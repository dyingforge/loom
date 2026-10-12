# ANSWERS：演示数据出处与真实模式验证

## 演示数据出处

演示模式的数据是固化在 `bundle/main.splash` 里的固定数据集，走与真实模式完全相同的应用路径：

- 任务拆分（compose）：四项任务，`demo-1` 检查新增记录 0.5 小时、`demo-2` 检查列表 0.5 小时、`demo-3` 检查本地保存 0.5 小时、`demo-4` 编写讲解说明 1 小时（依赖前三项）。定义在 `demo_tasks`。
- 计划块（compose）：四个时间块按「下一个工作日 09:00 起」顺序排布（09:00–09:30、09:30–10:00、10:00–10:30、10:30–11:30）。定义在 `demo_compose_blocks`。
- 一次修改（revise）：新增独立任务 `demo-0` 演示设备检查 0.5 小时，安排在其他任务之前，其余任务顺延。定义在 `demo_revise_tasks` / `demo_revise_blocks`。
- 一次追问（clarify）：问题是「新增的「演示设备检查」希望安排在上午 09:00 还是下午 14:00 开始？」，回答后以固定数据完成候选。定义在 `demo_clarify`。

时间块相对「现在」动态排布（`next_workday` 取今天之后的第一个工作日），保证 C1（时间块在未来）、C3（工作日工作时段）、C5（工时一致）、C6（不重叠）始终成立；任务依赖保证 C4 成立。目标是用户在界面填写的文本，演示模式只要求截止日期有效，不依赖固定目标文本。

## 真实模式验证证据

真实模式与演示模式的差异只在「规划数据从哪来」：

- 真实模式：`host.request("model.complete", …)` 返回模型输出，`apply_plan_result` 做 C1–C7 增量核验，失败丢弃并重试一次。
- 演示模式：`host.request("model.complete", …)` 返回 `no service answers "model" on this device` 后，`on_model_error` 置 `demo_mode`，`start_demo_planning` 用固化数据走同一条 `apply_plan_result` → `commit_candidate` 路径。

因此演示模式真实覆盖了「应用结果」这一段的全部代码：候选块生成 id、C1–C7 校验、diff 生成 changes、`plan_project` 应用方案、`verify_calendar_reasons` 确认核验、receipt 写入。六个阶段的模型输出内容与一次修正重试在本机无法验证（card-host 未注册 `model` 服务），记入未验证清单；真实闭环需 OctoSense 桌面 + 用户自配 provider。

## 自测证据

- `python3 scripts/check_demo.py`：演示闭环全自动走通（生成→计划卡→确认→核验→保存→月历→修改→追问→重启恢复），输出见 `results.json`。
- `hub check bundle --allow-unsigned`：PASSED，grants `{"model", "storage"}`。
