# 目标日历演示

## 运行准备

验证环境为 macOS Apple Silicon、Python 3.9.6、Rust 1.89，模型为 MiniMax-M2.7。Python 依赖记录在 `requirements.txt`。

| 组件 | 固定提交 |
| --- | --- |
| OctoSense-App-Hub | `78dfda5f33638e1869c36bceef5713342aae861c` |
| Makepad | `c155f61d0e1600d2ec474209374444a38a09a470` |
| octoscript-makepad | `2cc5ef37d7d6a3d2992673389ce74488f7bb2d87` |
| octoscript | `f67cb843dddb045a75a13b7d166994fc13acd17c` |

`native/LOCK.json` 记录 OctoSense-App-Hub 及其 `Cargo.toml` 引用的 Makepad、octoscript-makepad 与 octoscript 四个官方仓库的地址、提交与构建命令。按固定来源准备并构建原生宿主：

```sh
python3 scripts/build_native.py
python3 scripts/build_native.py --verify   # 只验证锁定记录与现有源码，不构建
```

脚本在被 Git 忽略的 `.scratch/native` 中检出四个官方提交，执行 `cargo build --release --locked` 构建 `hub` 和 `card-host`，不使用 `git apply` 改写依赖源码。构建产物位于 `.scratch/native/OctoSense-App-Hub/target/release/`。

新设备先按官方 OctoScript-App-Design-Flow 的 `docs/QUICKSTART.md` 准备 Rust 与系统依赖，然后运行 `python3 scripts/build_native.py`。本机的默认客户端路径为 `.scratch/native/OctoSense-App-Hub/target/release/card-host`，使用 `python3 scripts/run_client.py` 启动；`run_client.py` 会拒绝未按锁定来源构建的宿主。

提交服务使用环境文件中的 MiniMax 凭据，由服务端通过 `LOOM_ENV_FILE` 加载。启动本机单个 Uvicorn 进程：

```sh
python3 -m pip install -r requirements.txt
LOOM_ENV_FILE=/path/to/.env PORT=8010 LOOM_USAGE_DB=$PWD/.scratch/service/loom.sqlite3 \
LOOM_DAILY_COST_LIMIT_CENTS=1000 LOOM_RATE_LIMIT=60 python3 scripts/run_dev_server.py
```

当前提交实例使用 `PORT=8010`、`LOOM_USAGE_DB=.scratch/service/loom.sqlite3`、每日公共额度 1000 美分、每 IP 每分钟 60 次，凭据来自 `LOOM_ENV_FILE` 指定的环境文件。

客户端通过 `https://tariff-boards-bradley-theory.trycloudflare.com` 访问本机服务。保持服务和当前 Cloudflare 隧道运行。需要重新创建开发隧道时运行：

```sh
.scratch/native/cloudflared tunnel --url http://127.0.0.1:8010 --no-autoupdate --protocol http2
```

将新地址填写到 `bundle/main.splash` 的 `api_origin`，将裸域名填写到 `bundle/manifest.json` 的 `network.hosts`。隐私入口固定为 `bundle/listing.json` 中版本标签的 GitHub 文档，不随隧道变化。

启动应用：

```sh
python3 scripts/run_client.py
```

启动窗口为 1440×1000，默认数据目录为 `.local-state/calendar`。客户端固定东八区（UTC+8），不读取设备时区文件。日历使用 `state-a.json` 与 `state-b.json` 交替保存的完整 JSON 快照，从空白月历开始。

## 演示操作

1. 在顶部输入目标：“完成阅读记录应用的演示准备：检查新增记录和列表、本地保存、编写讲解说明，每项约半小时至一小时。”截止日期填写七天后的真实日期。
2. 选择“生成计划”。等待模型自动拆分任务、查询工作时段并检查安排。候选任务直接显示在月历中。
3. 选择有任务的日期，在下方查看当天完整安排。每天的格子显示两项任务，额外任务显示数量提示。右侧显示真实任务数量、工时、期限和安排理由。
4. 选择“确认计划”。应用保存候选内容，实际回读文件并核验，核验通过后显示正式日历。
5. 在右侧填写建议：“请新增一个独立任务‘演示设备检查’，工时0.5小时，安排在所有其他任务之前，原有任务标题与工时保持。”选择“根据建议修改”。
6. 查看新候选计划。通过“查看已确认计划”和“查看候选计划”切换日历。选择“确认修改后的计划”，等待保存核验完成。
7. 关闭并重新启动应用，检查正式日历与核验结果。候选计划也可以在确认之前关闭并恢复。

“上个月”“下个月”切换真实月份，“今天”返回当前月份并选中当天。修改目标或截止日期使用顶部“编辑目标”。模型需要补充说明时，通过右侧输入框回答并继续。

## 自动验证

`scripts/check_release.py` 是发布验收入口，依次运行官方宿主与真实文件存储检查、真实客户端目标生成/修改/确认/重启/候选与正式切换、真实中断服务与重新确认、真实客户端草稿与追问、真实服务错误与额度检查，以及最终 `hub check`。结果写入 `.scratch/release-check/`：

```sh
LOOM_ENV_FILE=/path/to/.env python3 scripts/check_release.py
```

单独运行真实客户端日历流程时，使用空的数据目录启动真实客户端并驱动各阶段：

```sh
python3 scripts/run_client.py --hidden --state .scratch/calendar-demo
python3 scripts/check_demo.py --state .scratch/calendar-demo
```

`check_demo.py` 读取 `<state>/loom.pm-calendar/state-a.json` 与 `state-b.json` 中序号最大的记录，用真实控件文本验证正式/候选切换，用保存后的业务记录验证阶段与正式项目。`--phase verify-failure` 在服务中断时验证确认失败并保留候选，`--phase retry-confirm` 在服务恢复后验证重新确认。

## 使用范围

演示面向单用户、单设备和应用内日历。工作时间为周一至周五 09:00–18:00，截止日期对应当天 18:00。输入接受未来一年内的有效日期。设备时间固定为东八区（UTC+8），用于解释无偏移日历时间。

每次计划最多包含十二项任务。未来时间块为模型计算和用户确认预留至少十五分钟。已经开始或完成的工作记录受到保护。生成与修改需要有效 HTTPS 服务和模型凭据；失败时显示真实原因，并提供重新生成或重新确认入口。

布局、尺寸、字体与交互通过 Figma 数据和客户端控件信息核对。当前验收使用结构与几何信息。
