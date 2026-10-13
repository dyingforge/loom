# 目标日历演示

## 运行准备

验证环境为 macOS Apple Silicon、Python 3.9.6、Rust 1.89。客户端零服务化，不需要 Python 服务、模型密钥或 HTTPS 隧道。

| 组件 | 固定提交 |
| --- | --- |
| OctoSense-App-Hub | `655114c4943cd2490daaefa2173e7b5aaa20669f` |
| Makepad | `c155f61d0e1600d2ec474209374444a38a09a470` |
| octoscript-makepad | `2cc5ef37d7d6a3d2992673389ce74488f7bb2d87` |
| octoscript | `f67cb843dddb045a75a13b7d166994fc13acd17c` |

`native/LOCK.json` 记录 OctoSense-App-Hub 及其 `Cargo.toml` 引用的 Makepad、octoscript-makepad 与 octoscript 四个官方仓库的地址、提交与构建命令。按固定来源准备并构建原生宿主：

```sh
python3 scripts/build_native.py
python3 scripts/build_native.py --verify   # 只验证锁定记录与现有源码，不构建
```

脚本在被 Git 忽略的 `.scratch/native` 中检出官方提交，执行 `cargo build --release --locked` 构建 `hub` 和 `card-host`，不使用 `git apply` 改写依赖源码。构建产物位于 `.scratch/native/OctoSense-App-Hub/target/release/`。

新设备先按官方 OctoScript-App-Design-Flow 的 `docs/QUICKSTART.md` 准备 Rust 与系统依赖，然后运行 `python3 scripts/build_native.py`。本机的默认客户端路径为 `.scratch/native/OctoSense-App-Hub/target/release/card-host`，使用 `python3 scripts/run_client.py` 启动；`run_client.py` 会拒绝未按锁定来源构建的宿主。

启动应用：

```sh
python3 scripts/run_client.py
```

启动窗口为 1440×1000，默认数据目录为 `.local-state/calendar`。客户端固定东八区（UTC+8），不读取设备时区文件。日历使用 `state-a.json` 与 `state-b.json` 交替保存的完整 JSON 快照，从空白月历开始。

## 演示操作

card-host 没有注册模型服务，客户端会在第一次「生成计划」时自动进入演示模式，右上角徽标从「由你的模型生成」切换为「演示数据」。

1. 在顶部输入目标：“完成阅读记录应用的演示准备：检查新增记录和列表、本地保存、编写讲解说明，每项约半小时至一小时。”截止日期填写七天后的真实日期。
2. 选择“生成计划”。演示模式用固化数据拆分四项任务并安排四个时间块，候选任务直接显示在月历中。
3. 选择有任务的日期，在下方查看当天完整安排。右侧显示真实任务数量、工时、期限和安排理由。
4. 选择“确认计划”。应用保存候选内容、回读文件并本地核验，核验通过后显示正式日历与「保存核验通过」。
5. 在右侧填写建议：“请新增一个独立任务‘演示设备检查’，工时0.5小时，安排在所有其他任务之前，原有任务标题与工时保持。”选择“根据建议修改”。演示模式提出一次追问，请回答后继续。
6. 在右侧输入框回答追问（例如“安排在上午 09:00 开始。”），选择“提交回答并继续”。查看新候选计划，通过“查看已确认计划”和“查看候选计划”切换日历。选择“确认修改后的计划”，等待保存核验完成。
7. 关闭并重新启动应用，检查正式日历与核验结果，徽标保持“演示数据”。候选计划也可以在确认之前关闭并恢复。
8. 选择当天安排里第一个时间块右侧的「标记完成」，右侧容量区的剩余工时随之减少；选择「重新安排剩余工作」，查看新候选计划后选择「确认修改后的计划」，等待保存核验完成。已完成的时间块可以随时「取消完成」回退。

“上个月”“下个月”切换真实月份，“今天”返回当前月份并选中当天。修改目标或截止日期使用顶部“编辑目标”。

## 自动验证

`scripts/check_demo.py` 是演示闭环的自动验收，用空的数据目录启动真实客户端并驱动各阶段，读取 `<state>/loom.pm-calendar/state-a.json` 与 `state-b.json` 中序号最大的记录做断言：

```sh
python3 scripts/check_demo.py
```

覆盖：生成→计划卡→确认→核验→保存→月历→修改→追问→标记完成→重排→重启恢复，并核对「演示数据」徽标。

`scripts/check_client_state.py` 检查草稿保存与重启恢复；`scripts/check_vectors_client.py` 驱动 card-host 复算 C1–C7 并逐条对齐 Python 参考输出。发布门禁：

```sh
.scratch/native/OctoSense-App-Hub/target/release/hub check bundle --allow-unsigned
```

## 使用范围

演示面向单用户、单设备和应用内日历。工作时间为周一至周五 09:00–18:00，截止日期对应当天 18:00。输入接受未来一年内的有效日期。设备时间固定为东八区（UTC+8），用于解释无偏移日历时间。

每次计划最多包含十二项任务。已经开始或完成的工作记录受到保护。宿主没有模型服务时自动进入演示模式；真实模式需要宿主接入模型提供方。失败时显示真实原因，并提供重新生成或重新确认入口。

计划可包含里程碑：月历以「◆ 里程碑」标记对应日期，选择日期可查看标题；里程碑日期早于预计完成时间时，右侧容量区给出提示。候选与正式计划的安排理由显示在右侧计划说明中。

布局、尺寸、字体与交互通过 Figma 数据和客户端控件信息核对。当前验收使用结构与几何信息。
