# 目标日历交付说明

应用使用 Figma 定义的顶部品牌栏、目标入口、月历、当天完整安排与右侧计划说明。颜色、字体、列宽、日期格尺寸和控件状态由设计数据确定。原生窗口默认 1440×1000，页面支持滚动查看完整内容。

用户填写目标和截止日期后，MiniMax 自动拆分任务并查询实际可用工作时段，将候选安排显示到月历。用户可以通过文字建议调整任务和时间。正式计划与候选分别保存；确认后实际回读已保存的候选数据并核验，通过后更新正式日历。

## 交付文件

- `bundle/main.splash`：原生目标日历与完整交互。
- `bundle/assets/fonts/`：Noto Sans SC、Manrope 和字体授权。
- `server/`：MiniMax 连接、任务重构、日历约束和保存核验。
- `scripts/run_client.py`：窗口与数据目录启动配置。
- `scripts/check_release.py`：发布验收入口。
- `scripts/check_demo.py`：真实控件、模型调用和恢复验证。
- `docs/DEMO.md`、`docs/PROTOCOL.md`、`docs/PRIVACY.md`：演示、协议与数据说明。

## 验证

环境为 macOS Apple Silicon、Python 3.9.6、按 `native/LOCK.json` 固定官方提交构建的 card-host、MiniMax-M2.7 和实际 Cloudflare HTTPS 连接。客户端固定东八区，本地业务记录使用 `state-a.json` 与 `state-b.json` 快照。

六十四项自动测试覆盖日历约束、保存核验、任务重构与工作记录保护、容量、权限、使用记录和架构。真实客户端与模型验收证据写入 `.scratch/release-check/`。界面按 Figma 数据和实际控件几何信息检查。

## 演示运行

启动步骤见 `docs/DEMO.md`。开发 HTTPS 地址要求本机服务和隧道持续运行。重新创建隧道后，需要同步客户端地址、主机清单和隐私说明链接。

交付使用按官方 `native/LOCK.json` 提交构建的本地 card-host。提交使用本机服务与 Cloudflare 临时 HTTPS 隧道，需要保持服务与隧道运行；提交资料包括真实截图与应用包检查。首次提交允许未签名，已有签名发布记录的后续提交需要使用登记密钥。具体资料见 [正式提交所需资料](OPEN_QUESTIONS.md) 和 [AppHub 发布准备](APPHUB_PUBLISHING.md)。
