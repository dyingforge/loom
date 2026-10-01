"""客户端 A/B 快照存储。

两份快照交替写入（`snap-a.json` / `snap-b.json`）。每份快照包含：
- sequence: 严格递增整数
- checksum: 基于内容 SHA-256 的十六进制摘要
- snapshot: 项目对象（含日历、固定日程、变更记录、版本号）

读时选择 sequence 较大且 checksum 校验通过的一份。
"""
from __future__ import annotations

import hashlib
import json
import pathlib


SLOT_A = "snap-a.json"
SLOT_B = "snap-b.json"


def _checksum(payload: dict) -> str:
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def _wrap(snapshot: dict, sequence: int) -> dict:
    body = {"sequence": sequence, "checksum": _checksum(snapshot), "snapshot": snapshot}
    body["checksum"] = _checksum(body)
    return body


def _verify(body: dict) -> bool:
    if not isinstance(body, dict):
        return False
    snapshot = body.get("snapshot")
    declared = body.get("checksum")
    if not isinstance(snapshot, dict) or not isinstance(declared, str):
        return False
    return _checksum({"sequence": body["sequence"],
                      "checksum": _checksum(snapshot),
                      "snapshot": snapshot}) == declared


def _read_slot(jail_dir: pathlib.Path, name: str) -> dict | None:
    path = jail_dir / name
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not _verify(body):
        return None
    return body


def _pick_target_slot(jail_dir: pathlib.Path) -> str:
    """选择要写入的槽位：始终写较旧的一份；首次写入槽 A。"""
    a = _read_slot(jail_dir, SLOT_A)
    b = _read_slot(jail_dir, SLOT_B)
    if a is None:
        return SLOT_A
    if b is None:
        return SLOT_B
    return SLOT_A if a["sequence"] <= b["sequence"] else SLOT_B


def write(jail_dir: pathlib.Path, snapshot: dict, sequence: int) -> dict:
    """写入指定 sequence 的快照到下一槽位；返回写入后的 body。

    写策略：先写入临时文件 `snap-tmp.json`，回读校验后再决定替换哪一个槽位。
    """
    body = _wrap(snapshot, sequence)
    jail_dir.mkdir(parents=True, exist_ok=True)
    tmp = jail_dir / "snap-tmp.json"
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    readback = json.loads(tmp.read_text(encoding="utf-8"))
    if not _verify(readback):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("snapshot write failed: checksum mismatch on readback")
    target = _pick_target_slot(jail_dir)
    (jail_dir / target).write_text(json.dumps(readback, ensure_ascii=False),
                                   encoding="utf-8")
    tmp.unlink(missing_ok=True)
    return readback


def load(jail_dir: pathlib.Path) -> dict | None:
    """读取最新有效快照。损坏或缺失的槽位被跳过。"""
    a = _read_slot(jail_dir, SLOT_A)
    b = _read_slot(jail_dir, SLOT_B)
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a if a["sequence"] >= b["sequence"] else b


def snapshot_to_project(body: dict) -> dict:
    """从 body 取出项目快照。"""
    return body["snapshot"]


def corrupt_demo(jail_dir: pathlib.Path, slot: str) -> None:
    """测试用：人为破坏一个槽位文件，验证 load 仍能恢复另一槽位。"""
    path = jail_dir / slot
    if path.exists():
        path.write_text("{not-json", encoding="utf-8")
