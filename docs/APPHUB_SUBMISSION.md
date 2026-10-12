# Submit loom.pm-calendar 0.1.0

## 提交信息

- 应用：`loom.pm-calendar`
- 版本：`0.1.0`
- 仓库：`https://github.com/dyingforge/loom`
- 标签：`v0.1.0`
- 应用包路径：`bundle/`
- 发布者：`dyingforge`
- 签名：`unsigned`（首次提交使用未签名应用包）
- 平台：macOS（Apple Silicon）
- 类别：`productivity`
- 能力：`storage`、`model`，存储额度 4 MiB，`agent` 为 `null`
- 官方宿主：`native/LOCK.json` 固定的 OctoSense-App-Hub 提交构建的 `card-host` 与 `hub`

## 官方检查输出

```text
loom.pm-calendar 0.1.0 — PASSED
  [warning] publisher-signature: unsigned: accountability rests on the hub alone
  grants: capabilities {"model", "storage"}, hosts {}, storage 4194304 bytes, agent none
```

带官方目录的 `hub check --allow-unsigned` 退出状态为 0，只有未签名提示。

## 1. 应用是否完成名称、副标题和描述宣称的功能

是。`bundle/listing.json` 描述为「填写目标与截止日期，Loom 自动拆分任务并安排到月历。查看每天的完整安排，通过文字建议调整任务与时间，确认并核验后保存正式计划。规划由宿主模型完成，无模型服务时自动使用内置演示数据。」

- 目标与截止日期入口：`bundle/main.splash` 的 `goal_input`、`deadline_input` 与 `generate_plan()`。
- 自动拆分并安排到月历：`start_model_planning()` 调用宿主 `host.request("model.complete", …)`，结果经 `apply_plan_result()` 写入 `app_state.draftProject`、`app_state.plan` 与 `app_state.calendar`，由 `calendar_grid` 绘制。
- 查看完整安排：`day_detail` 显示所选日期的全部时间块与依赖。
- 文字建议修改：`advice_input` 与 `revise_plan()` 触发 `revise`。
- 确认并核验后保存：`confirm_plan()`、`verify_pending()` 调用本地 `verify_calendar_reasons()`，通过后写入正式项目与核验回执。
- 保存到本地：客户端在应用目录交替写入 `state-a.json` 与 `state-b.json` 完整快照，写入后回读比较。
- 无模型服务时：`on_model_error()` 识别 `no service answers "model" on this device`，进入演示模式，用固化数据走同一链路。

真实验收：在官方宿主构建的 `card-host` 上，演示闭环全自动走通，包含目标生成、确认核验、文字修改、追问、重启恢复与本地文件存储检查。

## 2. 列表平台和类别是否适合此类应用

适合。应用是桌面端目标与月历工具，`platforms` 仅声明 `macos`，只声明实际验证过的平台；类别 `productivity` 对应日程与任务安排。界面按 1440×1000 窗口和真实控件几何验收。

## 3. 能力是否与应用可见行为一致

一致，没有多余授权。

- `storage`：客户端使用官方 `fs` 在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整快照，保存草稿、候选、正式项目、回执与演示标记。
- `model`：客户端只调用 `host.request("model.complete", …)` 请求宿主模型。宿主没有模型服务时进入演示模式。应用包不携带模型密钥。
- 没有授予相机、麦克风、位置、通讯录等与界面无关的能力；`agent` 为 `null`。清单不声明网络，也不请求任何网络主机。

## 4. 界面是否有欺骗性内容

没有。界面不模仿系统提示、支付界面、登录界面或其他品牌。功能按钮为「生成计划」「确认计划」「根据建议修改」「重新确认计划」等明确动作；状态区显示真实的保存、核验与失败原因。徽标明确区分「由你的模型生成」与「演示数据」。没有密码输入框。

## 5. 源码或数据中是否有面向助手的指令

没有。`main.splash` 只有界面文本、状态提示和面向用户的操作说明；`listing.json`、`manifest.json` 与 `docs/` 描述应用功能。源码注释是中文开发注释，不构成对助手或模型的指令。应用不读取本地文件系统中的任意内容作为提示。

## 6. 是否有辱骂性文字或指向特定个人

没有。界面、清单与文档中没有辱骂性内容，也没有指向任何私人个体；示例目标是通用演示目标。

## 7. 路由建议

建议 `pass`。

- 功能与描述一致，权限与实际行为一致，平台与类别匹配。
- 客户端使用官方宿主能力，保存全部在本机应用目录。规划通过宿主 `model.complete` 完成，无模型服务时使用内置演示数据；确认核验在客户端本地执行。
- 已通过官方 `hub check --allow-unsigned`，只有未签名提示。

## 远程处理

- 目标生成、文字修改、回答追问：客户端把当次需要的项目内容、当前时间与输入经宿主 `model.complete` 发送给宿主模型。
- 确认核验：客户端本地执行 `verify_calendar_reasons()`，不调用模型。
- 应用包不包含密钥、恢复凭据和个人数据；客户端不维护自有服务端。

## 验证状态

- 宿主：`native/LOCK.json` 固定官方 OctoSense-App-Hub 提交及其 `Cargo.toml` 引用的 Makepad、octoscript-makepad、octoscript 提交。
- 真实文件存储、东八区日期与初始截止日期、无设备时间文件、中文连续输入、重启恢复、部分写入恢复、全部记录无效停止：通过。
- 演示闭环（生成→计划卡→确认→核验→保存→月历→修改→追问→重启恢复）：`python3 scripts/check_demo.py` 通过。
- 约束核验 C1–C7 与 Python 参考逐条一致：`python3 scripts/check_vectors_client.py` 通过。
- 官方宿主正常流程下隔离预算为 4194304 字节存储、67108864 字节堆与 20000000 条指令，连续操作未触发任何上限错误。
- `hub check`：通过。截图：`bundle/screenshots/01-main.png` 来自真实客户端。
