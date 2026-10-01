# 目标日历演示

## 运行准备

验证环境为 macOS Apple Silicon、Python 3.9.6、Rust 1.89，模型为 MiniMax-M2.7。Python 依赖记录在 `requirements.txt`。

| 原生运行环境 | 提交编号 |
| --- | --- |
| OctoScript-App-Design-Flow | 本机 `.scratch/native/OctoScript-App-Design-Flow` 中的官方工具 |
| octoscript-makepad | `cb66de073469063abeb2a5ab2a2bbf3cdb365745` |
| makepad | `1f3b1dedfbb81424eb8dbf69e5e2c634fa73dc54` |
| octoscript | `dbd48cfb799551c11e30970c393777d29644a605` |

新设备按照官方 OctoScript-App-Design-Flow 的 `docs/QUICKSTART.md` 准备运行环境并构建 `card-host`。默认程序路径为 `.scratch/native/OctoSense-App-Hub/target/release/card-host`，其他路径可通过 `scripts/run_client.py --host` 指定。

在项目根目录的 `.env` 中填写 `MINIMAX_API_KEY`，参考 `.env.example`。启动服务：

```sh
python3 -m pip install -r requirements.txt
python3 scripts/run_dev_server.py
```

客户端通过 `https://quotes-geographical-per-foreign.trycloudflare.com` 访问本机服务。保持服务和当前 Cloudflare 隧道运行。需要重新创建开发隧道时运行：

```sh
.scratch/native/cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate --protocol http2
```

将新地址填写到 `bundle/main.splash` 的 `api_origin`，将裸域名填写到 `bundle/manifest.json` 的 `network.hosts`，同时更新 `bundle/listing.json` 的隐私说明地址。

启动应用：

```sh
python3 scripts/run_client.py
```

启动窗口为 1440×1000，默认数据目录为 `.local-state/calendar`。启动器读取设备时区。新日历使用独立的保存格式，从空白月历开始。

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

使用空的数据目录启动真实客户端，并执行控件验证：

```sh
python3 scripts/run_client.py --hidden --state .scratch/calendar-demo
python3 scripts/check_demo.py --state .scratch/calendar-demo
```

脚本验证跨年、六行月份、普通二月、闰年二月、无效日期、真实模型生成、当天完整安排、首次确认和文字建议修改。证据写入 `docs/evidence/calendar-demo.json`。

验证候选与正式计划恢复、确认修改后的计划：

```sh
curl -s http://127.0.0.1:8144/quit
python3 scripts/run_client.py --hidden --state .scratch/calendar-demo
python3 scripts/check_demo.py --state .scratch/calendar-demo --phase restore-candidate
```

再次关闭并启动，验证正式日历与核验回执恢复：

```sh
curl -s http://127.0.0.1:8144/quit
python3 scripts/run_client.py --hidden --state .scratch/calendar-demo
python3 scripts/check_demo.py --state .scratch/calendar-demo --phase restore
```

实际中断服务后，可以在候选状态运行 `--phase verify-failure`，检查确认失败时正式日历与候选内容仍然保存。重新启动服务和客户端后，运行 `--phase retry-confirm` 验证恢复核验。

## 使用范围

演示面向单用户、单设备和应用内日历。工作时间为周一至周五 09:00–18:00，截止日期对应当天 18:00。输入接受未来一年内的有效日期。设备当前 UTC 偏移用于解释无偏移日历时间；涉及未来夏令时变化时，需要确认时间安排。

每次计划最多包含十二项任务。未来时间块为模型计算和用户确认预留至少十五分钟。已经开始或完成的工作记录受到保护。生成与修改需要有效 HTTPS 服务和模型凭据；失败时显示真实原因，并提供重新生成或重新确认入口。

布局、尺寸、字体与交互通过 Figma 数据和客户端控件信息核对。当前验收使用结构与几何信息。
