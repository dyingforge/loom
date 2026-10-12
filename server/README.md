# server/（参考资产）

本目录是旧版服务端实现，已不再被客户端使用，仅作为参考资产保留：

- `domain/`：项目模型、约束检查（C1–C7）、容量计算与日历差异，其语义已在 `bundle/main.splash` 中用 OctoScript 重新实现。
- `agent/`：旧版真实模型的工具调用与规划过程，已由客户端的 `model.complete` 通道替代。
- `adapters/`：旧版 HTTP 服务与 MiniMax 连接，客户端不再使用。
- `runtime/`：方案应用与完整回读核验，对应客户端的 `plan_project` 与 `verify_calendar_reasons`。
- `tests/`：旧版参考测试，不再列入发布检查。

客户端的协议、约束语义与演示模式见 `docs/PROTOCOL.md`。
