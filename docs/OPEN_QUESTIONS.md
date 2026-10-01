# 未决口径与待人工决策

本文件记录实施过程中浮现、但实现侧无法自行决定的口径问题。每项都阻塞对应 ticket 的特定验收点；解出后由人工确认并删除条目。

## Q1 比赛资格与自建服务端

按 PRD 与 issues/01，需用户或赛事方确认“自建服务端 + OctoScript 客户端”是否在比赛资格范围内。未确认前不影响代码与测试，但阻断最终发布。

## Q2 公网域名与部署平台

按 PRD §3.4，需用户提供：
- 部署平台（Vercel / Cloudflare Workers / 自建 VPS 等）；
- 公网 HTTPS 入口域名（写入 `bundle/manifest.json` 的 `network.hosts`）。

## Q3 MiniMax 凭据与额度

按 PRD §3.4，需用户决定：
- 是否使用现有 `MINIMAX_API_KEY`，或新增；
- 每日费用上限数值（当前默认 1000 cents）；
- 评审专用额度发放方式（当前通过 `LOOM_REVIEWER_TOKEN` header 识别）。

## Q4 固定日程与批准例外的处理口径

按 PRD §三 / 硬约束，C2（不占用固定日程）属于不可执行约束；但同时 PRD §3.5 节提及“用户批准仅适用于当前方案，不永久扩大权限”，并暗示可能存在“移动固定日程”的批准例外。

按 README 当前口径：本仓库实现坚持 C2 不可豁免；如未来需要例外，应在 `constraints.md` 与 `vectors/c2_fixed_events.json` 中先明确例外向量，再修改 `server/domain/constraints.py`。

## Q5 C5 工时口径

PRD §二要求块总时长等于剩余工时；但实际项目中原工时不可直接获得，需要明确：
- 已完成块的累计时长是否计入原工时；
- 已发生但未完成块如何计入；
- 用户更新 `remainingHours` 时是否需要同时调整原工时。

按 README 当前口径：剩余工时为唯一进度口径，块用时不自动换算成任务进度；客户端在 `client/main.splash` 中标记块完成时提示用户更新 `remainingHours`，不自动扣减。

## Q6 同一候选校验计数

PRD 写“同一候选最多校验 4 次”，但未明确：
- 试校验（即模型自己 validate_schedule 调用）是否计入；
- 候选修订后是否重置计数。

按 README 当前口径：以循环最终校验为准；模型试校验不计。同一签名候选（含空候选）4 次后停止；不同候选分别计数。

## Q7 重启后的 Agent 上限

暂停上下文、调用次数与候选计数如何跨重启保留需要人工决策。

按 README 当前口径：暂停时整个 `state` 通过 A/B 快照持久化（包含 `llm_calls` / `invalid_streak` / `candidate_attempts`）；恢复时反序列化，恢复后计数继续累计，不重置。
