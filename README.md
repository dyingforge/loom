# Loom

OctoScript 客户端 + Python 服务端 + MiniMax 模型的项目经理日历 Agent。

## 项目结构

```
.
├── AGENTS.md                         # 本仓库工作规则
├── README.md                         # 本文件
├── constraints.md                    # 硬约束 C1–C7 人读文档
├── docs/                             # 设计文档与报告
│   ├── 项目经理日历 · 架构与实现方案（修订版）.md
│   ├── 项目经理日历 · AI 可执行实施计划（v2）.md
│   ├── PROTOCOL.md                   # 客户端 ↔ 服务端契约
│   ├── PROBE_REPORT.md               # 01 探针
│   ├── PROBE_REPORT_02.md            # 02 探针
│   ├── DECISIONS.md                  # 架构决策 D1–D13
│   ├── OPEN_QUESTIONS.md             # 未决口径
│   ├── PRIVACY.md                    # 隐私说明
│   ├── PROGRESS.md                   # 20 ticket 进度
│   └── RELEASE_REPORT.md             # 20 发布报告
├── vectors/                          # C1–C7 验证向量（双端共用）
├── server/                           # Python（FastAPI + Pydantic）
│   ├── domain/                       # 纯函数
│   ├── agent/                        # ports/tools/loop/limits
│   ├── adapters/                     # http + minimax
│   ├── runtime/                      # reconcile / version_check / executor
│   └── tests/                        # 96 项测试 + 脚本替身
├── client/                           # OctoScript 客户端
│   ├── domain.py                     # 独立实现的 C1–C7 校验器
│   ├── store.py                      # A/B 快照
│   └── main.splash                   # UI 入口
├── bundle/                           # 应用包
│   ├── manifest.json
│   ├── listing.json
│   ├── main.splash
│   ├── assets/icon.svg
│   └── screenshots/                  # 待 OctoScript 运行时补真实截图
├── fixtures/scenarios/scenarios.py   # 九个固定场景
└── scripts/
    ├── probe_minimax_basic.py        # 01 探针脚本
    ├── probe_minimax_scheduling.py   # 02 探针脚本（10 次真实调用）
    ├── build_vectors.py              # 重新生成 vectors/
    └── run_dev_server.py             # 本地联调入口
```

## 快速开始

```sh
# 1. 安装依赖
pip install fastapi uvicorn pydantic pytest pytest-asyncio httpx

# 2. 跑全部测试
PYTHONPATH=. python3 -m pytest server/tests/ client/tests/

# 3. 启动开发服务端（脚本替身模式）
PYTHONPATH=. python3 scripts/run_dev_server.py

# 4. 切到真实模型
set -a && source .env && set +a
LOOM_USE_REAL_MODEL=1 PYTHONPATH=. python3 scripts/run_dev_server.py

# 5. 重跑 MiniMax 探针（10 次真实调用）
set -a && source .env && set +a
PROBE_RUNS=10 python3 scripts/probe_minimax_scheduling.py > .scratch/probe02.json
```

## 当前状态

- 96 项 Python 测试通过（无 API key 时）；含 API key 时 99 项全过；
- 9 项场景脚本化通过；
- 真实 MiniMax 端到端测试 3 项全过（平均 30 秒/次）；
- 依赖守卫断言 `domain` 不 import `agent/adapters`、`agent` 不 import `adapters`；
- 应用包结构符合 OctoScript `hub check` 规则（密钥、登录表单、密码字段均无）。

未在本环境验证：OctoScript 运行时实跑（card-host 缺）、`hub check` / `hub scan` 命令、真实截图与录屏。详见 `docs/RELEASE_REPORT.md` 与 `docs/OPEN_QUESTIONS.md`。
