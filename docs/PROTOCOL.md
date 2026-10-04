# Loom 日历协议

## 时间与项目

项目使用设备所在地的无偏移 ISO 日历时间，例如 `2026-10-01T09:00:00`。启动器向客户端提供设备时区与当前 UTC 偏移。请求中的 `now` 必填，时间包含偏移时拒绝处理。休息日编号为 `0=周一` 至 `6=周日`。

项目包含 `id`、非负 `version`、`goal`、`deadline`、`milestones`、`tasks`、`fixedEvents`、`workHours`、`restDays`、`preferences`、`autoAdjust`。任务包含 `id`、`title`、`priority`、`remainingHours`、`done`、`dependsOn`、`adjustable`、`blocks`。完整类型定义位于 `server/domain/models.py`。

## 生成与修改

客户端发送 `POST /v1/agent/jobs`，包含 `snapshot`、`now`、`trigger`、`instruction`。生成目标使用 `trigger=compose`；根据建议修改使用 `trigger=revise` 和非空 `instruction`。目标与有效的未来截止时间必须存在。

服务立即返回 `202` 和 `jobId`。客户端使用 `GET /v1/agent/jobs/{jobId}` 查询，每次最多等待十五秒。执行中返回 `status=running` 和实际工具执行阶段 `stage`；结束时返回 `status=complete` 和 `result`。服务重启或过程过期返回 `410`。服务最多同时执行四项规划。

| 结果字段 | 含义 |
| --- | --- |
| `type` | `plan`、`tasks`、`clarify` 或 `failed` |
| `draftProject` | 生成或修改后的完整候选任务清单 |
| `payload` | 计划、问题、候选任务或停止原因 |
| `proposed_tasks` | 任务建议操作提出的候选任务 |
| `resumeToken` | 暂停时签发的恢复凭据，仅 `clarify` 返回 |
| `capacity` | 剩余工时、期限内可用工时与缺口 |
| `calendar` | ISO 时间与日历秒数的对应数据 |

服务独占完整模型会话、对话、工具调用结果与调用计数，只向客户端返回上表中的展示字段。

`compose` 必须调用 `rebuild_tasks` 完成目标拆分。`revise` 根据建议调整任务内容、工时、依赖或时间。重构保留已经开始或完成的工作记录。模型查询真实空闲时段，提交完整排程，并接受工时、依赖、工作时间、固定日程和冲突核验。

计划包含 `planId`、`baseVersion`、`changes`、`rationale`、`risks`、`exceptions`。每项变更包含 `blockId`、`before`、`after`。候选清单与候选日历分别通过 `draftProject` 和计划变更表示，正式项目在确认前保持保存状态。

## 确认与核验

客户端检查计划版本和原始时间块，根据 `draftProject` 应用变更，产生版本增加一次的完整目标日历。候选目标先写入 `pendingVerification`，同时保留正式项目。

客户端实际回读保存文件，将 `beforeSnapshot`、`draftProject`、`plan`、`readbackSnapshot` 和当前 `now` 发送至 `POST /v1/calendar/verify`。服务比较完整预期数据与回读数据，复核日历约束以及已经开始或完成的记录。

服务返回 `verified` 或 `not_verified` 回执。核验通过后，客户端将目标日历保存为正式项目并再次回读比较；候选与待核验记录清空。失败时保留正式项目、候选与待核验目标，显示具体原因并提供重新确认入口。

## 保存与恢复

客户端交替写入 `calendar-a.json` 和 `calendar-b.json`，格式版本为三。每份记录包含 `sequence`、`payload`、`mirror`，两份正文必须一致，读取序号较大的记录。保存后使用原生结构比较检查全部内容。损坏内容立即停止处理。

记录包含正式项目、候选任务、计划、时间资料、输入建议、核验回执、待核验目标、显示月份和选中日期。候选与正式计划支持分别查看和重新启动恢复。执行中的 `jobId` 可以继续查询；服务连接失效后显示停止原因。

## 补充回答

`type=clarify` 时，客户端显示问题并保存服务端返回的 `resumeToken` 与展示字段。恢复请求包含 `trigger=resume`、当前项目、当前时间、`clarificationAnswer` 和独立的 `resumeToken`，不再携带任何模型会话数据。

服务使用 SQLite 中的暂停状态继续规划。恢复凭据有效期二十四小时，凭据自身携带可解析的过期时间，服务签发新凭据时清理过期会话；过期凭据无论记录是否已清理都返回 `410` 与 `resume_expired`。恢复时先校验凭据所属项目，校验通过才标记消费，项目不符返回 `409` 与 `resume_project_mismatch` 且不消费凭据。未知有效期内凭据返回 `404` 与 `resume_unknown`，已消费凭据返回 `409` 与 `resume_consumed`。每轮最多调用模型十次，同一候选最多提交核验四次，计数由服务保存。
