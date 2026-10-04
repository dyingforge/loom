# 按 native/LOCK.json 准备并构建 Loom 原生宿主。
#
# 四个原生依赖固定在 native/LOCK.json。其中两个带 Loom 修复的仓库，其提交保存为
# native/bundles 下的 Git 提交包，含固定上游基线的干净仓库可以用 Git 验证并取回，
# 不需要重新应用补丁。本脚本只使用标准库与 git、cargo 命令：验证锁定记录、提交包
# 与现有检出的提交、干净状态和 origin，在 .scratch/native 中检出固定源码，从提交包
# 取回精确修复提交，然后执行 cargo build --release --locked 构建 hub 与 card-host，
# 并在二进制旁写入构建标记。不使用 sed、替换命令或 git apply 改写依赖源码。

import argparse
import hashlib
import json
import os
import subprocess
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "native" / "LOCK.json"
SCRATCH = ROOT / ".scratch"
TEMP = SCRATCH / "native-temp"
LOG_PATH = SCRATCH / "native-build.log"
STAMP_NAME = "native-build.json"


def _env():
    env = dict(os.environ)
    # 中间文件只放在被忽略的 .scratch 中，不使用系统临时目录。
    env["TMPDIR"] = str(TEMP)
    return env


def _tail(path, lines):
    # 日志文件在命令运行前已创建，直接读取末尾内容。
    with path.open("r", errors="replace") as handle:
        return "".join(deque(handle, maxlen=lines))


def streamed(args, *, cwd=None):
    # 大输出（cargo、clone、fetch）写入日志，不在内存中缓存整份输出。
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log:
        log.write(("$ " + " ".join(str(arg) for arg in args) + "\n").encode())
        log.flush()
        result = subprocess.run(
            [str(arg) for arg in args],
            cwd=cwd,
            env=_env(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        raise SystemExit(
            "命令失败（退出码 {}）：{}\n日志末尾：\n{}".format(
                result.returncode, " ".join(str(arg) for arg in args), _tail(LOG_PATH, 30)
            )
        )
    return result


def query(args, *, cwd=None, check=True):
    # 查询类命令输出很小，单独读取，失败时只带 stderr。
    result = subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(
            "命令失败（退出码 {}）：{}\n{}".format(
                result.returncode, " ".join(str(arg) for arg in args), detail
            )
        )
    return result


def git_query(repo, *args, check=True):
    return query(["git", "-C", repo, *args], check=check)


def git_stream(repo, *args):
    return streamed(["git", "-C", repo, *args])


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
    git_query(repo, "bundle", "verify", str(bundle))
    heads = trimmed(git_query(repo, "bundle", "list-heads", str(bundle)))
    if entry["fix"] not in heads:
        raise SystemExit("{} 提交包不包含修复提交 {}".format(entry["name"], entry["fix"]))


def check_origin(entry, repo):
    origin = git_query(repo, "remote", "get-url", "origin", check=False)
    if origin.returncode != 0:
        raise SystemExit("{} 缺少 origin，拒绝使用：{}".format(entry["name"], repo))
    url = trimmed(origin)
    if url != entry["url"]:
        raise SystemExit(
            "{} origin 不匹配，拒绝覆盖：{} != {}".format(entry["name"], url, entry["url"])
        )


def verify_checkout(entry):
    repo = checkout_path(entry)
    if not repo.is_dir():
        raise SystemExit("{} 缺少源码目录：{}".format(entry["name"], repo))
    if not (repo / ".git").exists():
        raise SystemExit("{} 不是 Git 仓库：{}".format(entry["name"], repo))
    head = trimmed(git_query(repo, "rev-parse", "HEAD"))
    if head != entry["fix"]:
        raise SystemExit(
            "{} 提交不符：{}\n  期望 {}\n  实际 {}".format(entry["name"], repo, entry["fix"], head)
        )
    dirty = trimmed(git_query(repo, "status", "--porcelain"))
    if dirty:
        raise SystemExit("{} 工作区不干净，拒绝覆盖：\n{}".format(entry["name"], dirty))
    check_origin(entry, repo)
    return head


def ensure_checkout(entry):
    repo = checkout_path(entry)
    if not repo.exists():
        git_stream(ROOT, "clone", entry["url"], str(repo))
    elif not (repo / ".git").exists():
        raise SystemExit("{} 路径已存在且不是 Git 仓库，拒绝覆盖：{}".format(entry["name"], repo))
    check_origin(entry, repo)
    dirty = trimmed(git_query(repo, "status", "--porcelain"))
    if dirty:
        raise SystemExit("{} 工作区不干净，拒绝覆盖：\n{}".format(entry["name"], dirty))
    head = trimmed(git_query(repo, "rev-parse", "HEAD"))
    if head == entry["fix"]:
        return
    # 修复提交来自版本管理的提交包，不来自重新应用的补丁；提交包要求本地已有
    # 固定上游基线。
    baseline = git_query(repo, "cat-file", "-e", "{}^{{commit}}".format(entry["upstream"]), check=False)
    if baseline.returncode != 0:
        git_stream(repo, "fetch", "origin")
        baseline = git_query(repo, "cat-file", "-e", "{}^{{commit}}".format(entry["upstream"]), check=False)
        if baseline.returncode != 0:
            raise SystemExit(
                "{} 缺少固定上游基线 {}，无法取回提交包".format(entry["name"], entry["upstream"])
            )
    if entry.get("bundle"):
        bundle = check_bundle_file(entry)
        git_stream(repo, "fetch", str(bundle), entry["bundle_ref"])
    git_stream(repo, "checkout", "--detach", entry["fix"])
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
    streamed(["cargo", "build", "--release", "--locked", *packages], cwd=repo)
    binary = repo / "target" / "release" / "card-host"
    if not binary.is_file():
        raise SystemExit("构建后没有找到 {}".format(binary))
    stamp = {
        "lock_sha256": sha256_file(LOCK_PATH),
        "card_host_sha256": sha256_file(binary),
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
    if not args.verify:
        # 每次构建重新开始一份日志，避免日志无限增长。
        LOG_PATH.write_text("")
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
