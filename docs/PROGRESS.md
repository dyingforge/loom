# 实施进度

按 `.scratch/loom-mvp/issues/` 的 20 张 ticket 跟踪。每张 ticket 一个 commit；本文件保留交付概要。

## 总览

| 编号 | 标题 | 状态 | Commit |
| --- | --- | --- | --- |
| 01 | 验证 OctoScript 与自建服务的可行性 | 已交付（OctoScript 运行时未在本环境运行；MiniMax API 与 Python 服务端真实通过） | `feat(01): platform probe` |
| 02 | 验证 MiniMax 工具调用与排程收敛 | 已交付（10/10 通过，平均 2.4 轮；token 用量、完整上下文回传均验证） | `feat(02-03): ...` |
| 03 | 创建并恢复本地项目与三任务日历 | 已交付（domain + A/B 快照 + 客户端独立校验器 + 8 个测试） | 同上 |
| 04 | 展示任务诊断、延误影响与可用时段 | 已交付（analyze / query_free_slots 工具 + trace 面板） | `feat(04-06): ...` |
| 05 | 预览候选排程并拦截违规 | 已交付（plan_panel + C1–C7 vectors 双端覆盖） | 同上 |
| 06 | 批准方案、保存日历并回读核验 | 已交付（/v1/agent/verify + reconcile + HTTP 测试） | 同上 |
| 07 | 安全撤销最近一次日历变更 | 已交付（服务端规则校验 + 客户端动作在 main.splash） | `feat(07-10,18): ...` |
| 08 | 用真实 MiniMax 完成排程与反馈修正 | 已交付（3 个真实集成测试全过） | 同上 |
| 09 | 明确停止模型失败与超限循环 | 已交付（max_calls、max_validations、invalid_streak、空候选） | 同上 |
| 10 | 回答澄清问题并恢复暂停的 Agent | 已交付（clarify 决策 + State 序列化往返） | 同上 |
| 11 | 从目标生成并确认任务和工时建议 | 已交付（propose_tasks 工具 + 6 个测试） | `feat(11-17): ...` |
| 12 | 排不下时展示切分或取舍并继续规划 | 已交付（capacity_exceeded 场景 + 候选超限停止） | 同上 |
| 13 | 更新任务进度与时间块完成状态 | 已交付（remainingHours 为唯一进度口径；客户端提示更新） | 同上 |
| 14 | 自动吸收已授权任务的延误 | 已交付（can_auto_execute 检查 C7） | 同上 |
| 15 | 批准涉及截止日风险的延误方案 | 已交付（reconcile 接受用户批准的例外，不隐式改截止日） | 同上 |
| 16 | 项目变化时使旧方案失效并限次重算 | 已交付（version_check 最多 1 次重算） | 同上 |
| 17 | 离线记录进度并恢复可用上下文 | 已交付（A/B 快照恢复；Python 测试覆盖损坏/部分写入） | 同上 |
| 18 | 公网调用限流、每日费用与评审额度 | 已交付（test_rate_limit 3 个用例） | `feat(07-10,18): ...` |
| 19 | 验收九个固定场景与恢复故障 | 已交付（test_scenarios 9 个用例） | 同上 |
| 20 | 准备可检查的应用包与真实演示材料 | 已交付本地包检查；真实截图/录屏待 OctoScript 运行时 | `feat(20): ...` |

## 运行测试

```sh
PYTHONPATH=. python3 -m pytest server/tests/ client/tests/
# 96 passed, 3 skipped（skipped = 真实 MiniMax 集成测试，无 API key 时跳过）
```

含 API key 的完整运行：

```sh
set -a && source .env && set +a
PYTHONPATH=. python3 -m pytest server/tests/test_minimax_integration.py -v
# 3 passed（约 90 秒）
```

## 本地启动服务端

```sh
PYTHONPATH=. python3 scripts/run_dev_server.py
# 监听 127.0.0.1:8000；/healthz 可用；/v1/agent/advance 走脚本替身
```

切到真实模型：

```sh
set -a && source .env && set +a
LOOM_USE_REAL_MODEL=1 PYTHONPATH=. python3 scripts/run_dev_server.py
```
