# Loom 客户端协议

Loom 是零服务化的自包含客户端：规划由宿主提供的 `model.complete` 完成，宿主没有模型服务时自动使用内置演示数据。本文件描述客户端内部的持久化格式、与宿主的交互契约、约束核验语义与演示模式。

## 时间与项目

项目使用东八区（UTC+8）的无偏移 ISO 日历时间，例如 `2026-10-01T09:00:00`。客户端固定该时区，不读取设备时区文件。休息日编号为 `0=周一` 至 `6=周日`。

项目包含 `id`、非负 `version`、`goal`、`deadline`、`milestones`、`tasks`、`fixedEvents`、`workHours`、`restDays`、`preferences`、`autoAdjust`。任务包含 `id`、`title`、`priority`、`remainingHours`、`done`、`dependsOn`、`adjustable`、`blocks`。时间块包含 `id`、`taskId`、`start`、`end`、`done`。里程碑为 `{title, date}`，`date` 是 `YYYY-MM-DD` 日历日；拆分阶段可由模型产出，月历以「◆ 里程碑」标记并在容量区做期限风险提示。`autoAdjust` 表示项目是否允许自动调整，为 true 时候选与确认核验额外执行 C7。完整类型定义位于 `server/domain/models.py`（参考资产，客户端在 OctoScript 中重新实现同名语义）。

## 状态文件

客户端在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整 JSON 快照。每份对象顶层 `schema` 为 1，包含：

- `sequence`：严格递增的保存序号。
- `businessVersion`：每次业务提交增加一次的版本号。
- `business`：完整业务对象，含正式项目 `project`、候选任务 `draftProject`、计划 `plan`、核验回执 `receipt`、待核验目标 `pendingVerification`、日历 `calendar`、容量 `capacity`/`formalCapacity`、阶段 `phase`、追问 `question`/`questionId`/`workingProject`、演示标记 `demoMode`、显示月份与选中日期。
- `draft`：输入草稿，含 `projectId`、`questionId`、`revision`、`goal`、`deadline`、`answer`。

每次保存写入另一份文件，立即回读文本比较并检查必要字段，成功后才更新已保存序号与业务版本；失败就停止当前操作。启动时读取两份文件，选择序号最大的完整记录；一份不完整时恢复另一份并提示中断保存；两份都不存在时初始化；存在但没有有效记录时停止初始化并保留文件。业务提交与草稿保存复用同一入口，草稿保存只增加 `revision`，不增加 `businessVersion`。

## model.complete 交互契约

客户端通过 `host.request("model.complete", {task, input, schema, class: "strong"}, callback)` 请求宿主模型。`task` 是当次指令，`input` 是只含当次所需字段的数据，`schema` 是必填 JSON Schema。回调返回 `r.is_ok`、`r.data.output` 或 `r.error`。

规划分阶段进行，模型只写理解和方案，执行与核验不经过模型：

1. 拆分任务：`task` 为「把目标拆分为任务列表」，`input` 含目标、截止日期、当前时间、工作时间、休息日、固定日程、已有任务、修改建议与追问回答，`schema` 为 `schema_tasks`。输出 `{tasks: [...]}`，可附 `milestones`（里程碑）与 `question`（追问，见下文）。
2. 排程：`task` 为「为任务安排时间块，保留已完成与已开始块的编号和时间不变」，`input` 含拆分结果与 `slots`（客户端预计算的未来 14 天空闲时段列表，供模型参考），`schema` 为 `schema_blocks`。输出 `{blocks: [...]}`，可附 `rationale`（安排理由）与 `risks`（风险），展示在计划说明与容量区。
3. 核验修正：排程结果未通过约束时，把违规码 `violations` 连同原块送回模型修正一次；仍不通过则停止，进入可重试的失败态。
4. 提交：通过增量核验后，候选计划写入 `draftProject`/`plan`/`calendar`/`capacity`，阶段为 `candidate`。
5. 执行闭环：用户在当天安排中把时间块标记为完成，这是本地业务提交：`block.done=true`，任务 `remainingHours` 扣减块时长，无未完成块且工时归零时任务完成，`project.version` 增加，容量重算后经双快照保存，不经过模型。随后可发起 `trigger=progress` 的重排：跳过任务拆分，直接用现有任务排程；已完成与已开始块由 C1 锁定，其余走与修改建议完全相同的候选→确认→核验→保存链路。

### 各阶段 Schema

`schema_tasks`（拆分任务输出，小于 8 KiB）：

```json
{"type":"object","required":["tasks"],"additionalProperties":false,
 "properties":{"tasks":{"type":"array","maxItems":64,"items":{
   "type":"object","required":["id","title","priority","remainingHours","dependsOn","adjustable"],
   "additionalProperties":false,"properties":{
     "id":{"type":"string","minLength":1,"maxLength":80},
     "title":{"type":"string","minLength":1,"maxLength":200},
     "priority":{"type":"integer","minimum":1,"maximum":5},
     "remainingHours":{"type":"number","minimum":0,"maximum":720},
     "dependsOn":{"type":"array","maxItems":32,"items":{"type":"string"}},
     "adjustable":{"type":"boolean"}}}},
 "question":{"type":"string","minLength":1,"maxLength":300},
 "milestones":{"type":"array","maxItems":8,"items":{
   "type":"object","required":["title","date"],"additionalProperties":false,"properties":{
     "title":{"type":"string","minLength":1,"maxLength":80},
     "date":{"type":"string","minLength":10,"maxLength":10}}}}}}
```

`schema_blocks`（排程输出，小于 8 KiB）：

```json
{"type":"object","required":["blocks"],"additionalProperties":false,
 "properties":{"blocks":{"type":"array","maxItems":512,"items":{
   "type":"object","required":["taskId","start","end"],
   "additionalProperties":false,"properties":{
     "taskId":{"type":"string","minLength":1,"maxLength":80},
     "start":{"type":"string","minLength":16,"maxLength":19},
     "end":{"type":"string","minLength":16,"maxLength":19},
     "done":{"type":"boolean"}}}},
 "rationale":{"type":"string","minLength":1,"maxLength":800},
 "risks":{"type":"array","maxItems":8,"items":{"type":"string","maxLength":200}}
}
```

### 追问

真实与演示模式都支持追问。真实模式下阶段一输出非空 `question` 即进入追问（`enter_clarify`）：问题写入 `question`、候选项目写入 `workingProject`、阶段为 `clarify`。演示模式中 `revise` 触发一次固化追问（`demo_clarify`）。用户回答后以 `trigger=resume` 把回答拼进 `input.clarificationAnswer` 继续规划；追问回答走无状态调用，不保存任何服务端会话。

## 约束核验语义（工具语义）

`apply_plan_result` 是模型输出的唯一入口：为候选块生成 `id`，把候选任务写入 draft（保留同 id 任务的已有块、`adjustable` 与 `done`），再做 `validate_codes` 增量核验。核验按 C1–C7 就地检查候选块：

- C0：任务编号与时间块编号不重复，块归属任务存在。
- C1：已经开始或完成的时间块必须完整保留；新增块必须属于未完成任务且从当前时间以后开始。
- C2：不与固定日程冲突。
- C3：时间块完整位于工作日的工作时段。
- C4：任务依赖无环，未完成任务排在依赖任务之后。
- C5：未来未完成块总工时与剩余工时一致。
- C6：时间块互不重叠。
- C7：变更不涉及未授权自动调整的任务；仅在项目允许自动调整（`autoAdjust=true`）时判定，手动确认的候选不受 C7 限制。

通过后 `diff_blocks` 生成 `changes`，`plan_project` 按变更应用到 draft 得到候选日历。确认时 `verify_calendar_reasons` 复核版本一致、工作时间与固定日程不变、已完成记录不变、应用方案与回读一致，并再次跑 C1–C7；通过则写核验回执 `{planId, versionBefore, versionAfter, readbackSnapshot, status: "verified", reason}`，正式项目版本增加一次，候选与待核验记录清空。

## 演示模式

宿主对 `model.complete` 返回 `no service answers "model" on this device` 时，客户端进入演示模式（`demo_mode`），徽标从「由你的模型生成」切换为「演示数据」。演示数据是固化的完整数据：四项任务、四个计划块、一次修改（新增「演示设备检查」）、一次追问，覆盖 生成→计划卡→确认→核验→保存→月历→修改→追问 全链路；progress 重排的数据由当前正式快照派生（任务与时间块原样保留，含用户标记的完成状态），覆盖 标记完成→重排→确认 链路。演示数据走与真实模式完全相同的 `apply_plan_result`/`commit_candidate`/`verify_calendar_reasons` 路径，时间块按「下一个工作日 09:00 起」排布以保证约束始终成立。演示数据出处与验证证据见 `review/ANSWERS.md`。

## 宿主环境要求

- 客户端在 OctoSense 宿主（`card-host`）中运行，清单能力为 `["storage", "model"]`，不声明网络。
- `storage`：应用目录读写 `state-a.json`/`state-b.json`，额度 4 MiB。
- `model`：调用 `host.request("model.complete", …)`。宿主没有注册模型服务时进入演示模式，客户端不崩溃。
- 宿主由 `native/LOCK.json` 固定的官方提交构建，`run_client.py` 核对构建标记。

## 拒绝码与预算

模型调用失败全部显示为可重试的失败态，不崩溃：

- 无 provider 或无模型服务：宿主返回 `no service answers "model" on this device`，进入演示模式。
- 预算超限、频率限制、provider 失败：宿主的错误消息原样显示在失败态，提供「重新生成计划」重试入口。
- 输出非法：缺少 `tasks`/`blocks` 字段时显示「模型未返回任务列表」/「模型未返回时间块」，可重试。
- 约束核验失败：先送回模型修正一次，仍失败显示违规码，可重试。

宿主对单次 `model.complete` 的指令预算、频率与输出体积由宿主强制执行；客户端只对 `task`/`input`/`schema` 做字段裁剪，`task` 不超过 4 KiB，`input` 不超过 32 KiB，Schema 不超过 8 KiB。

## 自建复现步骤

```sh
# 1. 按锁定来源构建原生宿主（hub 与 card-host）
python3 scripts/build_native.py

# 2. 核对 bundle
.scratch/native/OctoSense-App-Hub/target/release/hub check bundle --allow-unsigned

# 3. 打开客户端
python3 scripts/run_client.py

# 4. 演示闭环自测（card-host 无模型服务时自动走演示模式）
python3 scripts/check_demo.py

# 5. 客户端状态自测（草稿保存与重启恢复）
python3 scripts/check_client_state.py
```

`server/` 目录是旧版服务端实现的参考资产，客户端不再使用；`vectors/` 是约束核验的共用测试数据，客户端用 `run_vector_check` 在 card-host 内复算并逐条对齐 Python 输出。
