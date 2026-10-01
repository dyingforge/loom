# 《项目经理日历》AI 可执行实施计划（v2：精简分层版）

> 依据：修订版 PRD。先定架构（第一部分），再列任务（第二部分）及其余事项。 标【默认】的是我替你选的技术决定；标【待探针确认】的依赖阶段 0 的结果，**执行 AI 不得凭猜测补全，必须先验证**。 我没有读过 OctoScript 仓库，客户端目录与 API 细节一律以仓库 `AGENTS.md`、`docs/SCRIPT-API.md` 为准。 v2 改动：服务端改为"纯核心＋外壳"三层；工具由 7 个缩为 3 个；删除 guard 模块与手写 schema；模拟模型移入 tests。

---

## 第零部分：给执行 AI 的工作规则

1. **一次只做一张任务卡**，按编号顺序，依赖未完成不得开始。
2. 每张卡必须交付：代码、测试、验收命令的实际输出。验收未通过不得标记完成。
3. **不得**：写死模型回复冒充真实结果；在运行时代码中保留任何模拟模型；在应用包中放密钥；扩大 PRD 范围；违反 1.2 的依赖规则。
4. 遇到 PRD 没写或与平台冲突的地方，**停下并记录到 `docs/OPEN_QUESTIONS.md`**，不自行决定。
5. 每完成一张卡，更新 `docs/PROGRESS.md`（卡号、日期、验收输出、遗留问题）。
6. 不引入依赖注入框架、插件式注册、抽象基类层级。一个 `Protocol` 加普通函数即可。

---

## 第一部分：项目架构

### 1.1 总体结构

```
┌───────────────────────────┐      HTTPS/JSON      ┌─────────────────────────────┐
│ OctoScript 客户端          │ ───────────────────▶ │ Python 服务端                │
│  · ui / api                │  推进 Agent          │  · adapters（HTTP、MiniMax） │
│  · executor / store        │  核验执行结果        │  · agent（循环、工具）       │
│  · domain（校验器）        │ ◀─────────────────── │  · domain（纯函数，无 IO）   │
└───────────────────────────┘  澄清/方案/失败       └─────────────────────────────┘
```

职责边界（不可越界）：

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| 模型 | 拆任务、估工时、提出排程、读校验反馈修正、解释取舍、追问 | 状态、权限、成败判定 |
| 服务端 | 工具执行、硬约束校验、方案差异、回读核验 | 持久化项目数据、执行日历变更 |
| 客户端 | 存储、权限、执行、回读、撤销、独立复核硬约束 | 调用模型、保存密钥 |

### 1.2 依赖规则（唯一的架构铁律）

**依赖箭头只能向内：`adapters → agent → domain`。** 反向 import 一律禁止。

- `domain`：纯函数，无 IO、无框架、不知道"模型"存在。
- `agent`：只依赖 `domain` 和自己定义的接口（`ports.py`），不 import 任何具体提供方或 Web 框架。
- `adapters`：唯一接触外部世界的地方（HTTP、MiniMax、限流）。

这条规则用一个测试强制执行（见 T1）。

### 1.3 仓库结构【默认】

```
/
├─ server/                    # Python（FastAPI + Pydantic）【默认】
│  ├─ domain/
│  │  ├─ models.py            # Project/Task/Block/Plan/Receipt（Pydantic，类型的唯一来源）
│  │  ├─ constraints.py       # C1–C7：validate(project, candidate) -> list[Violation]
│  │  ├─ scheduling.py        # free_slots(project, range)、diff(project, candidate)
│  │  └─ structure.py         # 依赖环、缺失任务、工时与切分总量
│  ├─ agent/
│  │  ├─ ports.py             # class LLM(Protocol): 一个方法
│  │  ├─ tools.py             # 3 个工具：函数 + 参数 schema 同文件
│  │  ├─ loop.py              # step(state, llm) -> state'（纯状态转移）
│  │  └─ limits.py            # 全部上限常量
│  ├─ adapters/
│  │  ├─ minimax.py           # 实现 ports.LLM
│  │  └─ http.py              # FastAPI 两个路由 + 限流/额度中间件（同文件）
│  └─ tests/                  # 含脚本化测试替身（仅此处允许）
├─ vectors/*.json             # 校验测试向量：{input, expected_violations}，两端共用
├─ constraints.md             # 硬约束清单 C1–C7（人读文档，向量与实现的依据）
├─ client/                    # OctoScript 应用【结构以仓库规则为准，待探针确认】
│  ├─ domain     # 校验器（纯逻辑，与服务端独立实现）
│  ├─ store      # A/B 快照读写与恢复
│  ├─ executor   # 版本/权限检查 → 保存 → 回读 → 回执；撤销
│  ├─ api        # 与服务端通信
│  └─ ui
├─ fixtures/scenarios/        # 9 个固定场景，兼作测试与演示脚本
└─ docs/  PROGRESS.md  OPEN_QUESTIONS.md  DECISIONS.md  PRIVACY.md
```

**关键设计：双实现、单向量。** 客户端与服务端校验器分别实现，但都必须通过同一份 `vectors/`，从机制上保证两边一致。类型以 Pydantic 为准，需要时导出 JSON Schema，不手写第二份。

### 1.4 核心数据模型（写在 domain/models.py）

- **Project**：`id, version, goal, deadline, milestones[], tasks[], fixedEvents[], workHours, restDays[], preferences(text), autoAdjust(bool)`
- **Task**：`id, title, priority, remainingHours, done, dependsOn[], adjustable(bool), blocks[]`
- **Block**：`id, taskId, start, end, done`（设备本地时间，ISO 字符串）
- **Plan**：`planId, baseVersion, changes[{blockId, before, after}], risks[], exceptions[], rationale`
- **Receipt**：`planId, versionBefore, versionAfter, readbackSnapshot, status`
- **AgentRequest**：`snapshot, trigger, state?`；**AgentResponse**：`type(clarify|plan|failed), payload, trace[]`

### 1.5 工具与循环

**模型可调用的 3 个工具**（`agent/tools.py`，均为 domain 函数的薄包装）：

| 工具 | 作用 |
| --- | --- |
| `analyze` | 结构检查（依赖环、缺失、工时）＋延误影响与里程碑风险 |
| `query_free_slots(range)` | 扣除固定日程、已完成块、休息日后的空闲时段 |
| `validate_schedule(candidate)` | 试校验候选排程，返回违规明细 `[{code, blockId, detail}]`，只判断不代排 |

**不再是工具的部分**：

- 快照：每轮直接放入上下文，不设读取工具。
- 追问：模型的结构化最终输出之一 `{clarify: 问题}`，由循环转成暂停，不是工具调用。
- 方案差异：候选通过校验后，由循环调用 `domain.scheduling.diff` 生成 Plan，模型不参与。
- 核验：核验接口内部调用，不暴露给模型。

**循环 `step(state, llm) -> state'`**：

1. 把 state（请求、历史消息、校验次数）交给 `llm`，得到下一步：工具调用，或最终输出（`submit` 候选 / `clarify` 问题）。
2. 工具调用 → 校验参数 → 执行 → 结果追加进 state。
3. `submit` → **循环自己再次调用 `domain.constraints.validate`**，不信任模型之前的试校验；不通过则把违规明细追加回 state，继续。
4. 通过 → 生成 Plan，并按自动调整条件决定"可执行"或"待确认"。
5. state 可直接序列化。**暂停＝返回 state，恢复＝带着 state 再调 `step`**，不需要线程或长连接。

上限（`limits.py`，PRD 数字）：每轮最多 10 次模型调用；同一候选最多校验 4 次；同类无效参数连续 2 次停止；单次调用超时 30 秒、不自动重试；版本变化自动重算 1 次。任何停止都带原因，不返回预设答案，不隐式回退到固定算法。

### 1.6 状态机

```
建议 ──(自动调整条件全满足)──▶ 已更新 ──(回读一致)──▶ 已核验
 │                             ▲
 └─(需批准)─▶ 待确认 ──(用户批准且版本一致)─┘
任意阶段 ──▶ 已停止（带原因）；版本变化 ──▶ 重算 1 次，仍变则暂停
```

"已核验"仅表示保存结果与批准方案一致。

### 1.7 硬约束清单（constraints.md）

| 编号 | 约束 |
| --- | --- |
| C1 | 已完成块与已发生工作不移动 |
| C2 | 不占用固定日程 |
| C3 | 块完整落在单个工作时段内，且不在休息日 |
| C4 | 依赖顺序：后继块不早于前驱全部完成 |
| C5 | 每任务块总时长 = 剩余工时 |
| C6 | 块之间不重叠 |
| C7 | 被移动的任务均已标记可调整（仅"自动执行"路径检查） |

### 1.8 已锁定的架构决策（写入 DECISIONS.md）

依赖只能向内；不跨提供方降级；服务端不长期保存项目内容；密钥仅在服务端；无云端账户；时间按设备本地时间；撤销算一次修改、仅撤最近一次；失败不返回预设答案；限流与额度是 HTTP 中间件，不是业务模块。

---

## 第二部分：任务卡

### 2.1 阶段 0 · 探针与脚手架

**T0 读规则并做探针**

- 做：通读 OctoScript 仓库三份文档；用最小代码验证 ①客户端能否 HTTPS 调用公网服务 ②`storage` 读写与大小限制 ③文件操作限制 ④MiniMax 模型名、工具调用、完整上下文回传 ⑤让模型在 `validate_schedule` 反馈下为 3 任务排程，跑 10 次，记录一次通过率与平均校验轮数。
- 产出：`docs/PROBE_REPORT.md`，并据此更新 1.3 中 client 结构。
- 验收：报告含每项"通过/失败/限制"；任一失败则停下，等人类决策。
- 人类前置：比赛资格需**你**先确认。

**T1 脚手架、向量与依赖守卫**

- 做：建目录；写 `constraints.md`；为 C1–C7 各造正例/反例向量，另含组合场景；写 `tests/test_architecture.py`，扫描 import，断言 `domain` 不 import `agent/adapters`，`agent` 不 import `adapters` 或任何 Web/模型 SDK。
- 验收：架构测试通过；故意加一条违规 import 能使其失败；每条约束至少 2 个反例向量。

### 2.2 阶段 1 · 核心与最小循环

**T2 domain 层** — 实现 `models/constraints/scheduling/structure`。验收：`pytest server/tests/domain` 全绿，且跑通全部向量。 **T3 agent 层** — 实现 `ports.LLM`、3 个工具（含参数校验）、`step` 与 `limits`。验收：工具单元测试；非法参数被拒；`step` 在脚本化替身下覆盖：正常提交、违规后修正、追问、各上限停止、state 序列化往返。替身只在 `tests/`。 **T4 adapters/http 层（临时脚手架）** — 实现两个路由，先接一个**测试替身驱动的开发入口**（仅用于联调，放 tests 或 dev 脚本，不进入 `server/` 包），走通到"待确认"。验收：命令行脚本能完整跑出轨迹。 **T5 客户端存储与执行** — domain 校验器（过同一向量）、A/B 快照（序号＋校验值，单快照内含日历/变更记录/版本）、执行器、回读、撤销。验收：杀进程后重启可恢复；人为损坏一个快照仍能恢复；撤销符合 PRD 规则。 **T6 阶段 1 端到端** — 最小页面串联。验收：计划确实改变、重启可恢复、变更记录可查、撤销可用。

### 2.3 阶段 2 · 接入真实模型

**T7 minimax 适配器**

- 做：实现 `adapters/minimax.py`；接入 HTTP 层；移除 T4 的开发入口。
- 验收：①模型实际发出工具调用并据结果继续 ②违规候选被拦截后模型能修正（轨迹可见）③改工时/依赖/偏好结果随之变化 ④缺条件时追问 ⑤API 失败、参数错误、达上限均明确停止 ⑥`grep -ri mock server --include=*.py --exclude-dir=tests` 无结果；`agent/` 与 `domain/` 未因本卡被修改（验证换提供方只动 adapters）。

### 2.4 阶段 3 · 体验与场景

**T8 界面** — 目标输入、任务与切分建议确认、日历、进度更新、方案差异、确认（含"处理中"状态位）、核验状态、撤销入口、一步可达的"可调整"开关、**轨迹面板（优先级最高）**。 **T9 场景测试** — 按下表实现 `fixtures/scenarios`，每个有自动或半自动脚本。

| 场景 | 预期走向 |
| --- | --- |
| 可吸收延误 | 建议→已更新→已核验 |
| 影响截止日 | 建议→待确认→批准→已更新→已核验，保留风险 |
| 依赖循环 | 结构检查报错，不排程 |
| 缺关键信息 | 追问并暂停 |
| 排不下 | 校验报缺口，模型提切分/取舍，待确认 |
| 模型违规排程 | 被拦截，修正后通过 |
| 确认期间版本变化 | 重算 1 次，仍变则暂停 |
| 保存失败 | 不标已更新，保留待确认 |
| API 失败 | 明确停止 |

**T10 HTTP 中间件防护** — 在 `adapters/http.py` 加按 IP 限流、每日费用上限、评审专用额度。验收：超限返回明确错误；演示额度不受公共额度耗尽影响；中间件可单独关闭以便测试。

### 2.5 阶段 4 · 发布

**T11 发布准备** — 声明 `storage`/`net`/主机；检查包内无密钥；写 `PRIVACY.md`（说明模型提供方会收到规划内容与任务标题）；录制真实完整运行录屏；截图；记录本地检查结果，与"获准上架"分开记录。

---

## 第三部分：其余事项

### 3.1 测试策略

- domain：向量驱动，两端同跑，改约束先改向量。
- agent：脚本化替身覆盖循环分支。替身实现 `ports.LLM`，**仅存在于 tests/**。
- 架构：依赖守卫测试常驻 CI。
- 模型行为：用 9 个场景＋T0 通过率基准做回归，记录每次通过率。

### 3.2 风险与应对

| 风险 | 应对 |
| --- | --- |
| 模型排程一次通过率低 | 收紧"每任务最多块数"，或提示词要求先 `query_free_slots` |
| 平台限制与方案冲突 | T0 即暴露，写入 OPEN_QUESTIONS 等人类决策 |
| 比赛资格不兼容 | 先于 T1 解决 |
| 演示时 API 失败 | 录屏备份，如实说明 |
| 赶工 | 保两种延误、批准、核验、撤销、轨迹面板 |

### 3.3 范围守则（不做）

后台自动触发、多用户/云账户、多提供方切换、时区与夏令时、第三方日历同步、日历界面深度打磨、依赖注入框架与插件机制。

### 3.4 需要你（人类）决定

1. **比赛资格**是否兼容自建服务端（T0 前）。
2. 部署平台与公网域名。
3. MiniMax 的 API 额度与每日费用上限数值。
4. 评审专用额度的发放方式。

### 3.5 建议的第一条指令（交给执行 AI）

> 阅读 `AGENTS.md`、`docs/SCRIPT-API.md`、`docs/PUBLISHING.md` 与本计划，然后只执行 T0；完成后提交 `docs/PROBE_REPORT.md` 并停止，等待确认。