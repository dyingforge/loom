#!/usr/bin/env python3
"""Build the Loom native client from the dependency sources fixed in LOCK.json.

The four native repositories are pinned in ``native/LOCK.json``. Two of them
carry Loom's fixes; their commits are stored as Git bundles under
``native/bundles`` so a clean checkout of the fixed upstream baseline can verify
and fetch them without re-applying patches. This script:

* verifies ``native/LOCK.json``, the bundle checksums and the existing checkouts
  (commit, clean tree and origin), then, unless ``--verify`` was given,
* checks out each fixed source under the ignored ``.scratch/native`` directory,
  fetching the exact fix commit from the project's Git bundle, and
* runs ``cargo build --release --locked`` for ``hub`` and ``card-host`` and
  writes a build stamp next to them.

It uses only the Python standard library plus the ``git`` and ``cargo``
commands. It never rewrites a dependency source with a script, ``sed`` or
``git apply``, and it refuses to touch a checkout that is dirty or whose origin
does not match the lock.
"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "native" / "LOCK.json"
SCRATCH = ROOT / ".scratch"
TEMP = SCRATCH / "native-temp"
STAMP_NAME = "native-build.json"


def run(args, *, cwd=None, check=True):
    env = dict(os.environ)
    # Keep every intermediate file inside the ignored .scratch tree.
    env["TMPDIR"] = str(TEMP)
    result = subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and result.returncode != 0:
        raise SystemExit(
            "命令失败（退出码 {}）：{}\n{}".format(
                result.returncode, " ".join(str(arg) for arg in args), result.stdout
            )
        )
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", repo, *args], check=check)


def trimmed(result):
    return result.stdout.strip()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock():
    if not LOCK_PATH.is_file():
        raise SystemExit("缺少锁定记录：{}".format(LOCK_PATH))
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("schema") != 1:
        raise SystemExit("锁定记录 schema 必须是 1")
    repositories = lock.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != 4:
        raise SystemExit("锁定记录必须列出四个依赖仓库")
    for entry in repositories:
        for field in ("name", "url", "checkout", "upstream", "fix"):
            if not entry.get(field):
                raise SystemExit("锁定记录缺少字段 {}.{}".format(entry.get("name"), field))
    return lock


def checkout_path(entry):
    return ROOT / entry["checkout"]


def check_bundle_file(entry):
    bundle = ROOT / entry["bundle"]
    if not bundle.is_file():
        raise SystemExit("{} 缺少提交包：{}".format(entry["name"], bundle))
    digest = sha256_file(bundle)
    if digest != entry["bundle_sha256"]:
        raise SystemExit(
            "{} 提交包校验值不符：{}\n  期望 {}\n  实际 {}".format(
                entry["name"], bundle, entry["bundle_sha256"], digest
            )
        )
    return bundle


def verify_bundle(entry):
    if not entry.get("bundle"):
        return
    bundle = check_bundle_file(entry)
    repo = checkout_path(entry)
    if not repo.is_dir():
        raise SystemExit("{} 缺少源码目录，无法验证提交包：{}".format(entry["name"], repo))
    git(repo, "bundle", "verify", str(bundle))
    heads = trimmed(git(repo, "bundle", "list-heads", str(bundle)))
    if entry["fix"] not in heads:
        raise SystemExit("{} 提交包不包含修复提交 {}".format(entry["name"], entry["fix"]))


def check_origin(entry, repo):
    origin = git(repo, "remote", "get-url", "origin", check=False)
    if origin.returncode == 0 and trimmed(origin) != entry["url"]:
        raise SystemExit(
            "{} origin 不匹配，拒绝覆盖：{} != {}".format(entry["name"], trimmed(origin), entry["url"])
        )


def verify_checkout(entry):
    repo = checkout_path(entry)
    if not repo.is_dir():
        raise SystemExit("{} 缺少源码目录：{}".format(entry["name"], repo))
    if not (repo / ".git").exists():
        raise SystemExit("{} 不是 Git 仓库：{}".format(entry["name"], repo))
    head = trimmed(git(repo, "rev-parse", "HEAD"))
    if head != entry["fix"]:
        raise SystemExit(
            "{} 提交不符：{}\n  期望 {}\n  实际 {}".format(entry["name"], repo, entry["fix"], head)
        )
    dirty = trimmed(git(repo, "status", "--porcelain"))
    if dirty:
        raise SystemExit("{} 工作区不干净，拒绝覆盖：\n{}".format(entry["name"], dirty))
    check_origin(entry, repo)
    return head


def ensure_checkout(entry):
    repo = checkout_path(entry)
    if not repo.exists():
        run(["git", "clone", entry["url"], str(repo)])
    elif not (repo / ".git").exists():
        raise SystemExit("{} 路径已存在且不是 Git 仓库，拒绝覆盖：{}".format(entry["name"], repo))
    check_origin(entry, repo)
    dirty = trimmed(git(repo, "status", "--porcelain"))
    if dirty:
        raise SystemExit("{} 工作区不干净，拒绝覆盖：\n{}".format(entry["name"], dirty))
    head = trimmed(git(repo, "rev-parse", "HEAD"))
    if head == entry["fix"]:
        return
    # The fixed commit comes out of the versioned bundle, never a re-applied
    # patch. The baseline must be present for the bundle's prerequisite.
    baseline = git(repo, "cat-file", "-e", "{}^{{commit}}".format(entry["upstream"]), check=False)
    if baseline.returncode != 0:
        run(["git", "-C", repo, "fetch", "origin"])
        baseline = git(repo, "cat-file", "-e", "{}^{{commit}}".format(entry["upstream"]), check=False)
        if baseline.returncode != 0:
            raise SystemExit(
                "{} 缺少固定上游基线 {}，无法取回提交包".format(entry["name"], entry["upstream"])
            )
    if entry.get("bundle"):
        bundle = check_bundle_file(entry)
        git(repo, "fetch", str(bundle), entry["bundle_ref"])
    git(repo, "checkout", "--detach", entry["fix"])
    verify_checkout(entry)


def app_hub_entry(lock):
    for entry in lock["repositories"]:
        if entry["name"] == "OctoSense-App-Hub":
            return entry
    raise SystemExit("锁定记录没有 OctoSense-App-Hub")


def build(lock):
    entry = app_hub_entry(lock)
    repo = checkout_path(entry)
    packages = []
    for name in ("octosense-card-host", "octosense-app-hub"):
        packages.extend(["-p", name])
    run(["cargo", "build", "--release", "--locked", *packages], cwd=repo)
    binary = repo / "target" / "release" / "card-host"
    if not binary.is_file():
        raise SystemExit("构建后没有找到 {}".format(binary))
    stamp = {
        "lock_sha256": sha256_file(LOCK_PATH),
        "repositories": {item["name"]: item["fix"] for item in lock["repositories"]},
    }
    (binary.parent / STAMP_NAME).write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    print("原生宿主已按锁定来源构建：{}".format(binary.parent))


def main():
    parser = argparse.ArgumentParser(description="按 native/LOCK.json 准备并构建 Loom 原生宿主")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只验证锁定记录、提交包和现有源码，不构建",
    )
    args = parser.parse_args()
    TEMP.mkdir(parents=True, exist_ok=True)
    lock = load_lock()
    if args.verify:
        for entry in lock["repositories"]:
            verify_bundle(entry)
            verify_checkout(entry)
        print("锁定记录、提交包与现有源码验证通过")
        return
    for entry in lock["repositories"]:
        ensure_checkout(entry)
        verify_bundle(entry)
        verify_checkout(entry)
    build(lock)


if __name__ == "__main__":
    main()
