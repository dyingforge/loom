"""架构守卫：domain 不得 import agent/adapters/runtime；
agent 不得 import adapters 或任何 Web/模型 SDK。

违规时本测试失败（实施计划 1.2 唯一的架构铁律）。
"""
import ast
import pathlib

import pytest


SERVER = pathlib.Path(__file__).resolve().parents[1]


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _top_level_imports(path: pathlib.Path) -> list[tuple[str, int]]:
    src = _read_text(path)
    tree = ast.parse(src, filename=str(path))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            mod = node.module
            # 仅记录形如 a.b.c 的最上层包路径
            out.append((mod, node.lineno))
    return out


@pytest.mark.parametrize("sub", ["domain"])
def test_domain_does_not_import_agent_or_adapters(sub: str) -> None:
    base = SERVER / sub
    assert base.exists(), f"missing {base}"
    for py in base.rglob("*.py"):
        for name, lineno in _top_level_imports(py):
            top = name.split(".", 1)[0]
            assert top not in {"server"}, (
                f"{py}:{lineno} 从内部顶层 server 包导入，"
                f"domain 应当只使用相对引用或同包内模块"
            )
            for forbidden in ("server.agent", "server.adapters", "server.runtime"):
                if name == forbidden or name.startswith(forbidden + "."):
                    pytest.fail(f"{py}:{lineno} 违规导入 {name}（domain 不得依赖 agent/adapters/runtime）")


@pytest.mark.parametrize("sub", ["agent"])
def test_agent_does_not_import_adapters(sub: str) -> None:
    base = SERVER / sub
    assert base.exists(), f"missing {base}"
    for py in base.rglob("*.py"):
        for name, lineno in _top_level_imports(py):
            for forbidden in ("server.adapters",):
                if name == forbidden or name.startswith(forbidden + "."):
                    pytest.fail(f"{py}:{lineno} 违规导入 {name}（agent 不得依赖 adapters）")
            # 禁止 Web 框架与模型 SDK
            for forbidden_top in ("fastapi", "starlette", "openai", "anthropic",
                                  "urllib3", "requests"):
                if name == forbidden_top or name.startswith(forbidden_top + "."):
                    pytest.fail(f"{py}:{lineno} agent 不得直接依赖 {forbidden_top}")


def test_architecture_violation_triggers_test() -> None:
    """证明本测试能捕获违规：临时写一个 domain 文件 import agent，再清理。"""
    bad = SERVER / "domain" / "_guard_probe.py"
    bad.write_text("from server.agent import ports  # noqa\n", encoding="utf-8")
    try:
        violations: list[str] = []
        for py in (SERVER / "domain").rglob("*.py"):
            for name, lineno in _top_level_imports(py):
                if name.startswith("server.agent"):
                    violations.append(f"{py}:{lineno} {name}")
        assert violations, "guard 自检：应当检测到违规导入"
    finally:
        bad.unlink(missing_ok=True)
        # 移除缓存
        for cached in (SERVER / "domain").rglob("__pycache__"):
            if cached.is_dir():
                import shutil
                shutil.rmtree(cached)


def test_runtime_package_has_no_dev_responses() -> None:
    """server/adapters/http.py 与 server/agent/* 不得包含 dev_responses / 脚本替身默认。"""
    forbidden_strings = ["_dev_responses", "ScriptedLLM"]
    for sub in ("adapters", "agent", "runtime"):
        for py in (SERVER / sub).rglob("*.py"):
            txt = py.read_text(encoding="utf-8")
            for bad in forbidden_strings:
                if bad in txt:
                    pytest.fail(f"{py} 包含 {bad}；脚本替身与开发入口不得进入运行时包")

