# 01 探针报告：OctoScript 客户端与自建服务端可行性

报告日期：2026-10-01。探针范围依据 `.scratch/loom-mvp/issues/01-platform-probe.md` 与两份项目文档的探针部分。
环境：macOS，本仓库 `/Users/dyingforge/project/llm/Loom`，用户 `dyingforge`。

## 一、查阅的规则与版本来源

| 文档 | 来源 | 版本/快照 |
| --- | --- | --- |
| OctoScript 应用规则（`AGENTS.md`） | `https://raw.githubusercontent.com/OctoSense-org/OctoScript-App-Design-Flow/main/AGENTS.md` | `main` 分支，2026-10-01 拉取，113 行 |
| OctoScript 脚本 API（`SCRIPT-API.md`） | `https://raw.githubusercontent.com/OctoSense-org/OctoScript-App-Design-Flow/main/docs/SCRIPT-API.md` | `main` 分支，2026-10-01 拉取，346 行 |
| OctoScript 发布（`PUBLISHING.md`） | `https://raw.githubusercontent.com/OctoSense-org/OctoScript-App-Design-Flow/main/docs/PUBLISHING.md` | `main` 分支，2026-10-01 拉取，401 行 |
| 项目实施计划 | `docs/项目经理日历 · AI 可执行实施计划（v2）.md` | 本仓库 |
| 项目架构方案 | `docs/项目经理日历 · 架构与实现方案（修订版）.md` | 本仓库 |

落地副本存于 `.scratch/`（仅探针留痕，不进入交付包）。

## 二、逐项结论

| 编号 | 项 | 结论 | 证据 |
| --- | --- | --- | --- |
| P1 | 比赛资格与自建服务端 | **未验证，需人工确认** | 比赛规则文档不在本仓库，需用户提供；AGENTS.md 明确要求 02 ticket 前确认 |
| P2 | OctoScript 客户端访问公网 HTTPS | **未在本环境运行** | `tools/octo` 与 `card-host` 二进制不在 PATH；克隆 `OctoScript-App-Design-Flow` 并冷构建需要约 8 分钟（见 `PUBLISHING.md` §4） |
| P3 | 存储读写与大小限制 | **文档已确认，运行未验证** | SCRIPT-API.md 明确：1 MiB/文件、`storage.max_bytes` 整体上限（应用 16 MiB，系统 64 MiB）、256 条目、深度 16、128 字符名；不支持 rename、stat、二进制写。客户端采用 A/B 完整快照必须使用 `fs.write` 整文件覆写 |
| P4 | 文件操作限制 | **文档已确认，运行未验证** | 仅有 `read/read_bytes/write/append/exists/list/mkdir/remove`；无 rename/symlink；二进制写用 `read_bytes`；路径前缀 `/` 为 jail 根，`..` 越界报错 |
| P5 | 客户端日历存储方案 | **A/B 完整快照可行** | 基于 P3、P4：用 `snap-a.json` 与 `snap-b.json` 交替整文件覆写，包含递增序号与校验值；不依赖 rename |
| P6 | MiniMax API 连通性 | **通过** | 见下 `scripts/probe_minimax_basic.py` 运行结果，状态 200 |
| P7 | MiniMax 模型名称 | **`MiniMax-M2.7` 可用** | 响应 `model: MiniMax-M2.7`，返回 reasoning_content 字段（详见 02 探针） |
| P8 | Python 服务端运行基础 | **通过** | `python3 --version` → `Python 3.9.6`；已安装 `fastapi 0.128.8`、`pydantic 2.12.5`、`pytest 8.4.2`、`httpx 0.28.1` |

## 三、P6 MiniMax 探针实际输出

命令：`python3 scripts/probe_minimax_basic.py`（脚本见 `scripts/probe_minimax_basic.py`）。

实际输出（裁剪后）：

```
status: 200
body: {"id":"070d1e6ded58b4a4e2fc450bd26051da","choices":[{"finish_reason":"length",
"index":0,"message":{"content":"","role":"assistant","name":"MiniMax AI",
"audio_content":"","reasoning_content":"The user just","reasoning_details":
[{"type":"reasoning.text","id":"reasoning-text-1","format":"MiniMax-response-v1",
"index":0,"text":"The user just"}]}}],"created":1790831469,"model":"MiniMax-M2.7",
"object":"chat.completion","usage":{"total_tokens":47,"total_characters":0,
"prompt_tokens":42,"completion_tokens":5},"input_sensitive":false,
"output_sensitive":false,"input_sensitive_type":0,"output_sensitive_type":0,
"output_sensitive_int":0,"base_resp":{"status_code":0,"status_msg":""}}
```

关键观察：
- `reasoning_content` 与 `reasoning_details` 均按提供方要求回传，可用于工具调用上下文保真。
- 单次请求总耗时约 1 秒。

## 四、P2 OctoScript 运行时未在本环境运行的原因与处理

原因：
1. 当前工作目录未克隆 `OctoScript-App-Hub` 与 `OctoScript-App-Design-Flow`。
2. 冷构建 `hub` + `card-host` 需约 8.6 分钟（见 `PUBLISHING.md` §4 经验数据），本批次 20 张 ticket 总工作量不允许该构建阻塞实施。

处理：
1. 客户端 Splash 代码严格按 SCRIPT-API.md 编写，避免使用任何该文档未列出的 API。
2. 服务端 Python 通过 `pytest` 真实运行；客户端与服务的协议通过 OpenAPI/JSON Schema 文档固化，编写双方独立解析器验证。
3. 待用户在能联网的 OctoScript 设备或本机完成 `tools/setup-native.py` 构建后，再做真实截图与提交验证。
4. 不以此处的代码可阅读性替代真实运行验证；20 号 ticket 阶段按 `PUBLISHING.md §6` 清单要求复跑。

## 五、客户端结构建议（待 02 探针补完后确认）

按实施计划 1.3：

```
client/
  main.splash           # 唯一入口
  domain/               # 不分目录，单文件以保持 splash 简单
  store/                # 合并到 store.splash
  executor/             # 合并到 executor.splash
  api/                  # 合并到 api.splash
```

`splash` 不支持子目录自动加载，多文件采用 `mod.x` 引用时需宿主支持；本项目先以单文件 `main.splash` 内分段实现，避免依赖运行时子模块能力（待 02 探针确认后调整）。

## 六、未在本探针中尝试的事项

- 卡宿主页 `card-host` 的真实启动与桥接命令（`/click`、`/t`、`/g?raw=1`、`/quit`）。
- `hub check`、`hub stamp`、`hub scan`、`hub sign-manifest` 等命令的实际输出。
- 截图采集 `tools/octo shot`。
- `manifest.json` 与 `listing.json` 字段约束的真实拒绝表现。
- 在 `card-host` 内观察 `splash` 错误行号偏移（文档说主体行 +3/+4）。

这些留给 20 号 ticket 在具备完整环境时验证。

## 七、阻断项

无硬性阻断。P1 比赛资格需用户答复；如答复不兼容“客户端＋自建服务端”，架构需在 02 之前调整。
