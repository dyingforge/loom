# Loom 客户端与服务端协议

## 时间与项目

项目使用所在地的无偏移 ISO 日历时间，例如 `2026-10-01T09:00:00`。客户端以用户填写的 UTC 偏移计算当前时间，发送必填的 `now`。服务端直接检查日历时间。休息日编号为 `0=周一` 至 `6=周日`。

项目包含 `id`、非负 `version`、`goal`、可选 `deadline`、`milestones`、`tasks`、`fixedEvents`、`workHours`、`restDays`、`preferences` 和 `autoAdjust`。任务包含唯一 `id`、`title`、`priority`、`remainingHours`、`done`、`dependsOn`、`adjustable` 和 `blocks`。时间块包含 `id`、`taskId`、`start`、`end`、`done`。完整类型定义由 `server/domain/models.py` 提供。

里程碑包含 `id`、`title`、`due` 和 `taskIds`；空 `taskIds` 表示全部任务。更新项目事实递增版本，并作废待批准方案。剩余工时填写零表示任务完成；标记时间块完成会保留完成事实。

## 发起规划

客户端发送 `POST /v1/agent/jobs`，请求包含 `snapshot`、`now` 和 `trigger`。`trigger` 支持 `new`、`propose`、`progress`、`delay`、`resume`。服务立即返回 `202` 和 `jobId`。

客户端使用 `GET /v1/agent/jobs/{jobId}` 查询真实执行结果，每次查询最多等待 15 秒。响应为 `status=running`，或者 `status=complete` 及 `result`。服务重启或过程过期返回 `410`。服务最多同时执行四项规划。

`result` 包含以下字段：

| 字段 | 含义 |
| --- | --- |
| `type` | `tasks`、`plan`、`clarify`、`failed` |
| `payload` | 任务建议、方案、问题或停止原因 |
| `state` | 当前规划状态、对话、真实用量和累计计数 |
| `trace` | 实际工具调用和约束检查结果 |
| `capacity` | 剩余工时、期限内可用工时和缺口 |
| `calendar` | 方案时间与日历秒数的对应数据，供客户端独立复核 |

方案包含 `planId`、`baseVersion`、`changes`、`rationale`、`risks`、`exceptions`。每项变更包含 `blockId`、`before` 和 `after`。服务只生成方案，客户端在用户批准后保存日历。

`POST /v1/agent/advance` 使用相同请求与结果结构，等待整轮结束，供直接接口调用使用。

## 暂停与恢复

`type=clarify` 时，客户端显示 `payload.question` 并保存返回状态。恢复请求发送 `trigger=resume`、当前项目、当前时间、`clarificationAnswer` 和带有 `resumeToken` 的状态。

服务端使用 SQLite 中的真实暂停状态恢复规划。恢复凭据有效期 24 小时，使用一次后失效，调用与候选计数继续累计。每轮最多调用模型十次，同一候选最多提交检查四次。客户端提交的计数不能替换服务端记录。

## 保存与核验

批准前，客户端要求 `project.version == plan.baseVersion`，检查变更中的原始时间块，生成完整日历并独立复核约束。保存后项目版本增加一次。

客户端发送 `POST /v1/agent/verify`，包含 `plan`、`versionBefore`、`versionAfter`、`beforeSnapshot` 和实际文件回读的 `readbackSnapshot`。服务比较完整预期项目与回读项目，返回 `verified` 或 `not_verified` 回执。核验包括未修改的时间块、完成状态、任务信息和项目设置。

## 本地保存

客户端交替写入 `snap-a.json` 和 `snap-b.json`。每份记录包含 `sequence`、`payload` 与 `mirror`；两份内容一致时接受记录，选择序号较大的有效快照。保存后再次读取并比较完整内容。记录保留项目、待批准方案、暂停过程、核验回执和最近一次撤销资料。

模型或网络错误停止当前请求并显示错误。已保存但尚未核验的日历保留待核验记录，可以重新核验。客户端通过清单中明确声明的 HTTPS 主机访问服务。
