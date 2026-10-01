# 初赛主流程演示

## 运行准备

本机运行环境为 macOS Apple Silicon、Python 3.9.6 和 Rust 1.89。Python 依赖固定在 `requirements.txt`。真实模型使用 `MiniMax-M2.7`。

OctoScript 环境使用以下已构建版本：

| 项目 | 提交编号 |
| --- | --- |
| OctoScript-App-Design-Flow | 本机 `.scratch/native/OctoScript-App-Design-Flow` 中的官方工具 |
| octoscript-makepad | `cb66de073469063abeb2a5ab2a2bbf3cdb365745` |
| makepad | `1f3b1dedfbb81424eb8dbf69e5e2c634fa73dc54` |
| octoscript | `dbd48cfb799551c11e30970c393777d29644a605` |

新设备将官方 OctoScript-App-Design-Flow 放在 `.scratch/native/`，按照其中的 `docs/QUICKSTART.md` 准备上述运行环境并构建 `card-host`。也可以通过 `scripts/run_client.py --runtime` 指定已经准备好的官方工具目录。

模型密钥填写在本项目 `.env`。启动服务：

```sh
python3 -m pip install -r requirements.txt
python3 scripts/run_dev_server.py
```

客户端需要公开 HTTPS 入口。本机开发隧道正在将 `https://invitation-newport-commands-collections.trycloudflare.com` 转发到 `127.0.0.1:8000`。保持该隧道运行时，客户端可以直接使用已配置的地址。

重新创建开发隧道可以使用本机已安装的工具：

```sh
.scratch/native/cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate --protocol http2
```

该命令返回新的 HTTPS 地址。将 `bundle/main.splash` 中的 `api_origin` 和 `bundle/manifest.json` 中的 `network.hosts` 更新为新地址及裸域名，再启动客户端。固定服务同样需要公开 HTTPS、持续运行的 Python 服务和正确主机声明。

打开应用：

```sh
python3 scripts/run_client.py
```

## 操作步骤

1. 在“项目”填写目标：“完成阅读记录应用的初赛演示准备，包括检查新增记录与列表、本地保存验证和讲解说明。”填写所在地 UTC 偏移，保存项目。
2. 打开“方案”，选择“根据目标生成任务建议”。等待真实模型返回任务，查看标题、工时、优先级与依赖。通过“修改建议”修改标题或工时，然后确认全部任务建议。
3. 选择“生成排程方案”。查看安排理由、具体时间、容量和风险。规划使用真实空闲时段，为尚未开始的安排预留至少 15 分钟的计算与批准时间。
4. 选择“批准当前方案”。应用保存日历，实际回读文件并向服务核验。出现“日历已保存并核验”后，打开“日历”查看各任务时间块。
5. 打开“任务”，编辑某项任务的剩余工时并保存。打开“方案”，选择“根据当前进度重新规划”，查看变更后批准，等待核验完成。
6. 打开“过程”查看真实模型调用和排程检查。关闭并重新打开应用，确认项目、日历和核验回执已经恢复。

模型提出问题时，在“方案”填写明确回答并选择“提交回答并继续”。网络或模型错误会显示停止原因，保持服务连接可用后重新发起规划。

## 自动验证主流程

使用新的数据目录启动客户端：

```sh
python3 scripts/run_client.py --hidden --state .scratch/demo-check-state
python3 scripts/check_demo.py --state .scratch/demo-check-state
```

脚本实际点击控件、录入目标、调用模型、确认任务、批准日历并更新进度。结果写入 `docs/evidence/demo.json`。数据目录需要为空，才能从空项目进行验证。重复验证时使用新的目录名称。

验证重新启动恢复：

```sh
curl -s http://127.0.0.1:8144/quit
python3 scripts/run_client.py --hidden --state .scratch/demo-check-state
python3 scripts/check_demo.py --state .scratch/demo-check-state --phase restore
```

## 使用范围

演示面向单用户、单设备和应用内日历。工作时段和固定日程录入使用整点；任务工时可以填写小数。时间按用户填写的 UTC 偏移解释，跨夏令时需要维护偏移。日历安排以用户确认的剩余工时为依据，标记时间块完成后需要明确更新任务剩余工时。

临时 HTTPS 地址依赖本机服务和隧道持续运行。本次交付包含可运行客户端、真实模型服务、演示步骤和运行记录；应用商店签名、真实截图和正式提交资料由正式发布流程处理。
