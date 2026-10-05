# Submit loom.pm-calendar 0.1.0

## 提交信息

- 应用：`loom.pm-calendar`
- 版本：`0.1.0`
- 仓库：`https://github.com/dyingforge/loom`
- 标签：`v0.1.0`
- commit SHA：`<由编排者在发布提交确定后填写>`
- 应用包路径：`bundle/`
- 发布者：`dyingforge`
- 签名：`unsigned`（首次提交选择未签名，责任由应用包摘要与官方目录承担）
- 平台：macOS（Apple Silicon）
- 类别：`productivity`
- 能力：`storage`、`net`，存储额度 4 MiB，`agent` 为 `null`
- 官方目录：sequence `4`（2026-09-20）；`loom.pm-calendar 0.1.0` 不在目录中
- 官方宿主：`native/LOCK.json` 固定的 OctoSense-App-Hub `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1` 构建的 `card-host` 与 `hub`
- 服务地址：`https://tariff-boards-bradley-theory.trycloudflare.com`
- 审核问题包：`.scratch/apphub-release/review.json`

## 官方检查输出

```text
loom.pm-calendar 0.1.0 — PASSED
  [warning] publisher-signature: unsigned: accountability rests on the hub alone
  grants: capabilities {"net", "storage"}, hosts {"tariff-boards-bradley-theory.trycloudflare.com"}, storage 4194304 bytes, agent none
```

带官方目录的 `hub check --allow-unsigned` 退出状态为 0，只有未签名提示。

## 1. 应用是否完成名称、副标题和描述宣称的功能

是。`bundle/listing.json` 描述为「填写目标与截止日期，Loom 自动拆分任务并安排到月历。查看每天的完整安排，通过文字建议调整任务与时间，确认并核验后保存正式计划。」

- 目标与截止日期入口：`bundle/main.splash` 的 `goal_input`、`deadline_input` 与 `generate_plan()`。
- 自动拆分并安排到月历：`launch_request()` 与 `poll_planning()` 调用服务端 `/v1/agent/jobs`，结果写入 `app_state.draftProject`、`app_state.plan` 与 `app_state.calendar`，由 `calendar_grid` 绘制。
- 查看完整安排：`day_detail` 显示所选日期的全部时间块与依赖。
- 文字建议修改：`advice_input` 与 `revise_plan()` 调用 `trigger=revise`。
- 确认并核验后保存：`confirm_plan()`、`verify_pending()` 调用 `/v1/calendar/verify`，通过后写入正式项目。
- 保存到本地：客户端在应用目录交替写入 `state-a.json` 与 `state-b.json` 完整快照，写入后回读比较。

真实验收：在官方宿主构建的 `card-host` 上，真实客户端完成目标生成、文字修改、确认回读、重新启动、候选与正式切换、服务中断后重新确认，以及真实文件存储检查。

## 2. 列表平台和类别是否适合此类应用

适合。应用是桌面端目标与月历工具，`platforms` 仅声明 `macos`，只声明实际验证过的平台；类别 `productivity` 对应日程与任务安排。界面按 1440×1000 窗口和真实控件几何验收。

## 3. 能力是否与应用可见行为一致

一致，没有多余授权。

- `storage`：客户端使用官方 `fs` 在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整快照，保存草稿、候选、正式项目、回执与恢复状态。
- `net`：客户端只请求 `network.hosts` 中声明的 `tariff-boards-bradley-theory.trycloudflare.com`，用于 Python 服务的 `/v1/agent/jobs`、`/v1/agent/jobs/{id}` 与 `/v1/calendar/verify`。应用包不携带模型密钥。
- 没有授予相机、麦克风、位置、通讯录等与界面无关的能力；`agent` 为 `null`。

## 4. 界面是否有欺骗性内容

没有。界面不模仿系统提示、支付界面、登录界面或其他品牌。功能按钮为「生成计划」「确认计划」「根据建议修改」「重新确认计划」等明确动作；状态区显示真实的读取、保存、核验与失败原因。没有密码输入框。

## 5. 源码或数据中是否有面向助手的指令

没有。`main.splash` 只有界面文本、状态提示和面向用户的操作说明；`listing.json`、`manifest.json` 与 `docs/` 描述应用功能。源码注释是中文开发注释，不构成对助手或模型的指令。应用不读取本地文件系统中的任意内容作为提示。

## 6. 是否有辱骂性文字或指向特定个人

没有。界面、清单与文档中没有辱骂性内容，也没有指向任何私人个体；示例目标是通用演示目标。

## 7. 路由建议

建议 `pass`。

- 功能与描述一致，权限与实际行为一致，平台与类别匹配。
- 客户端使用官方宿主能力，保存全部在本机应用目录；只有用户发起的目标生成与修改会把项目内容和修改建议经声明的 HTTPS 主机发送到服务端，再由服务端发送给 MiniMax。
- 已通过官方 `hub check --allow-unsigned --catalog`，只有未签名提示。

## 远程处理

- 生成与修改：客户端把项目快照、当前时间和修改建议经声明的 HTTPS 主机发送到服务端 `/v1/agent/jobs`；服务端把这些内容与工具调用历史发送给 MiniMax 完成规划。
- 确认核验：客户端确认计划时，把原始项目、候选项目、计划和实际回读项目发送到同一服务的 `/v1/calendar/verify`。该请求只做本地约束与回读比较，**不调用 MiniMax**。
- 应用包不包含密钥、恢复凭据和个人数据；服务端密钥由 `LOOM_ENV_FILE` 指定的环境文件提供。

## 验证状态

- 宿主：`native/LOCK.json` 固定官方 OctoSense-App-Hub `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1` 及其 `Cargo.toml` 引用的 Makepad `c155f61d0e1600d2ec474209374444a38a09a470`、octoscript-makepad `2cc5ef37d7d6a3d2992673389ce74488f7bb2d87`、octoscript `5991dfae9344589e732b2605b530f788e8bbcd11`。
- 真实文件存储、东八区日期与初始截止日期、无设备时间文件、中文连续输入、重启恢复、部分写入恢复、全部记录无效停止：通过。
- 真实客户端目标生成、文字修改、确认回读、重启、候选与正式切换、服务中断确认失败与重新确认：通过。
- 官方宿主正常流程下隔离预算为 4194304 字节存储、67108864 字节堆与 20000000 条指令，本次连续操作未触发任何上限错误。
- 真实客户端草稿与追问、真实服务错误与额度检查、`hub check`：通过。
- 截图：`bundle/screenshots/01-main.png` 来自真实客户端 `/g?raw=1`，采集时界面为已生成候选计划且无错误状态。
