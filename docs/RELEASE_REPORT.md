# 初赛演示交付报告

交付范围为目标录入、真实模型提出任务、用户修改确认、完整排程、批准保存、实际回读核验、更新进度后的重新规划及重新启动恢复。

## 已具备的交付内容

- `bundle/main.splash`：真实 card-host 客户端，包含项目、任务、方案、日历和过程界面。
- `server/`：真实 MiniMax 工具调用服务，模型密钥通过环境提供。
- `scripts/run_dev_server.py` 与 `scripts/run_client.py`：服务和客户端启动入口。
- `scripts/check_demo.py`：通过原生控件验证主流程。
- `requirements.txt` 与 `.env.example`：固定依赖和服务配置。
- `docs/DEMO.md`、`docs/PROTOCOL.md`、`docs/PRIVACY.md`：演示步骤、协议和数据处理说明。

## 验证环境

macOS Apple Silicon；Python 3.9.6；官方 card-host 已构建运行；MiniMax-M2.7 真实 API；客户端 HTTPS 请求通过实际 Cloudflare 隧道到达本机 FastAPI 服务。

领域约束、完整核验、容量、权限、使用记录与架构检查共 50 项自动测试通过。主流程运行证据存放在 `docs/evidence/demo.json`，每步记录实际项目、版本、回执与提供方报告用量。

主流程已从空项目完成真实模型任务建议、用户修改确认、首次排程批准核验和进度更新后的重新规划核验。最终项目版本为 6，重新启动后恢复相同项目和核验回执。

## 演示配置与正式提交

当前应用使用已运行的开发 HTTPS 隧道，演示要求保持本机服务及隧道运行。临时域名变化后，需要更新客户端地址与主机清单。

客户端通过 card-host 的实际权限检查并运行。应用商店发布需要正式发布者资料、公开隐私入口、截图和签名。初赛演示使用本地客户端运行方式，正式提交资料记录在 `docs/OPEN_QUESTIONS.md`。

延期、容量不足和使用额度相关实现保留在代码中，对特殊情况的进一步验收安排在演示主流程之后。
