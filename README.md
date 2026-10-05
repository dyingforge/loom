# Loom

Loom 是使用 OctoScript 原生客户端、Python 服务和 MiniMax 的目标日历。填写目标和截止日期后，模型拆分任务并安排到真实月历。用户查看每日安排，通过文字建议修改计划，确认并完成保存核验。

## 启动服务

已验证环境：macOS Apple Silicon、Python 3.9.6。依赖版本记录在 `requirements.txt`。

```sh
python3 -m pip install -r requirements.txt
LOOM_ENV_FILE=/path/to/.env python3 scripts/run_dev_server.py
```

`LOOM_ENV_FILE` 指向服务端读取的环境文件，其中保存 `MINIMAX_API_KEY`；密钥仅由服务端读取。服务默认监听 `127.0.0.1:8000`，可用 `PORT` 调整；缺少密钥时启动失败。

## 构建并启动客户端

原生宿主由 `native/LOCK.json` 固定的依赖源码构建。首次使用或依赖更新后运行：

```sh
python3 scripts/build_native.py
```

脚本在被 Git 忽略的 `.scratch/native` 中检出四个官方提交，执行 `cargo build --release --locked` 构建 `hub` 和 `card-host`，并在二进制旁写入构建标记。只检查锁定记录与现有源码而不构建时运行：

```sh
python3 scripts/build_native.py --verify
```

构建完成后打开应用：

```sh
python3 scripts/run_client.py
```

`run_client.py` 会核对构建标记，未按锁定来源构建的旧原生宿主会被拒绝。客户端通过公开 HTTPS 服务请求模型，域名需要同时出现在 `bundle/main.splash` 的 `api_origin` 和 `bundle/manifest.json` 的 `network.hosts` 中。

## 演示与验证

[演示说明](docs/DEMO.md) 记录具体操作、运行环境和使用限制。

```sh
python3 -m pytest -q server/tests
LOOM_ENV_FILE=/path/to/.env python3 scripts/check_release.py
```

`scripts/check_release.py` 依次运行真实存储、真实客户端状态与日历、真实服务错误与额度检查及最终 `hub check`，结果写入 `.scratch/release-check/`。`scripts/check_demo.py` 读取 `state-a.json`/`state-b.json` 快照验证月历与计划流程，`scripts/check_service.py` 检查服务启动、超时、提供方错误和额度限制；真实模型检查需要 HTTPS 服务与模型凭据。

客户端固定东八区（UTC+8），本地业务记录保存在应用目录的 `state-a.json` 与 `state-b.json` 两份交替快照中。服务端使用 SQLite 保存暂停对话与使用额度。

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
