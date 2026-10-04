# Loom

Loom 是使用 OctoScript 原生客户端、Python 服务和 MiniMax 的目标日历。填写目标和截止日期后，模型拆分任务并安排到真实月历。用户查看每日安排，通过文字建议修改计划，确认并完成保存核验。

## 启动服务

已验证环境：macOS Apple Silicon、Python 3.9.6。依赖版本记录在 `requirements.txt`。

```sh
python3 -m pip install -r requirements.txt
python3 scripts/run_dev_server.py
```

启动前在项目根目录创建 `.env`，参考 `.env.example`，填写 `MINIMAX_API_KEY`。密钥仅由服务端读取。服务监听 `127.0.0.1:8000`，缺少密钥时启动失败。

## 启动客户端

本机已经构建真实 `card-host`。使用以下命令打开应用：

```sh
python3 scripts/run_client.py
```

新设备需要按照 `docs/DEMO.md` 中的版本准备 OctoScript 运行环境。客户端通过公开 HTTPS 服务请求模型，域名需要同时出现在 `bundle/main.splash` 的 `api_origin` 和 `bundle/manifest.json` 的 `network.hosts` 中。

当前开发连接通过已经运行的 Cloudflare 临时隧道访问本机服务。临时连接在隧道终止后失效，重新启动隧道需要更新上述两个位置。正式演示设备需要保持服务和隧道运行，或者配置持续运行的 HTTPS 服务。

## 演示与验证

[演示说明](docs/DEMO.md) 记录具体操作、运行环境和使用限制。[日历验收记录](docs/evidence/calendar-demo.json) 来自真实控件操作、真实模型响应和本地文件回读。

```sh
python3 -m pytest -q server/tests
```

`scripts/check_demo.py` 驱动真实客户端验证月历日期、目标生成、文字修改、确认核验及恢复，启动时使用空的数据目录。`scripts/check_service.py` 检查真实服务的启动、超时、提供方错误和额度限制，需要模型凭据。

## 代码与资料

- `bundle/main.splash`：目标入口、真实月历、当天完整安排和计划说明。
- `bundle/assets/fonts/`：Figma 使用的 Noto Sans SC 与 Manrope 字体。每个字体的 name table 内嵌完整 OFL 1.1 授权，原始授权文本保存在 `docs/licenses/`。
- `server/domain/`：项目模型、约束检查、容量计算和日历差异。
- `server/agent/`：真实模型的工具调用与规划过程。
- `server/adapters/`：HTTP 服务、MiniMax 连接、使用记录和额度限制。
- `server/runtime/`：方案应用、自动执行条件和完整回读核验。
- `vectors/`：日历约束的共用验证数据。
- `CONTEXT.md`、`constraints.md`、`docs/PROTOCOL.md`：领域词汇、约束和协议。

项目面向单用户、单设备和应用内日历。初赛交付范围及各项状态记录在 [实施进度](docs/PROGRESS.md) 和 [交付报告](docs/RELEASE_REPORT.md)。
