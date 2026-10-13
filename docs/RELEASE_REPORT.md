# 目标日历交付说明

应用使用 Figma 定义的顶部品牌栏、目标入口、月历、当天完整安排与右侧计划说明。颜色、字体、列宽、日期格尺寸和控件状态由设计数据确定。原生窗口默认 1440×1000，页面支持滚动查看完整内容。

用户填写目标和截止日期后，宿主模型自动拆分任务并安排时间块，候选安排显示到月历。用户可以通过文字建议调整任务和时间。正式计划与候选分别保存；确认后实际回读已保存的候选数据并在客户端本地核验，通过后更新正式日历。宿主没有模型服务时自动进入演示模式，用内置固化数据完成相同链路。

## 交付文件

- `bundle/main.splash`：原生目标日历与完整交互。
- `bundle/assets/fonts/`：Noto Sans SC、Manrope 和字体授权。
- `scripts/run_client.py`：窗口与数据目录启动配置。
- `scripts/check_release.py`：发布验收入口，串联存储、演示闭环、客户端状态、向量核验与 `hub check`。
- `scripts/check_demo.py`：真实控件、演示数据链路与恢复验证。
- `scripts/capture_screenshot.py`：驱动官方 card-host 完成演示流程并抓取主界面截图。
- `docs/DEMO.md`、`docs/PROTOCOL.md`、`docs/PRIVACY.md`：演示、协议与数据说明。
- `server/` 与 `vectors/`：旧版服务端参考资产与共用约束向量，客户端不再使用服务端。

## 验证

环境为 macOS Apple Silicon、Python 3.9.6、按 `native/LOCK.json` 固定官方提交构建的 card-host。客户端零服务化，不声明网络；固定东八区，本地业务记录使用 `state-a.json` 与 `state-b.json` 快照。

六十四项自动测试覆盖日历约束、保存核验、任务重构与工作记录保护、容量、权限、使用记录和架构，位于 `server/tests/`，作为参考资产保留并通过。发布验收以 `scripts/check_release.py` 为准，真实客户端证据写入 `.scratch/release-check/`。

演示闭环由 `scripts/check_demo.py` 全自动驱动。真实模式于 2026-10-12 在 OctoSense 桌面 RC4 与用户自配模型提供方下完整走通，含六阶段调用、宿主 schema 校验、C1–C7 增量核验、违规修正重试、确认核验与双快照保存，证据见 `review/ANSWERS.md`。

## 演示运行

启动步骤见 `docs/DEMO.md`。客户端自包含，不需要本机服务、模型密钥或 HTTPS 隧道。

布局修复：窗口宽度约 1000 布局点以下的目标输入行挤压已修复（目标输入列固定 560 宽，两种窗口尺寸验证通过），记录见 `review/ANSWERS.md`。

交付使用按官方 `native/LOCK.json` 提交构建的本地 card-host。提交资料包括真实截图与应用包检查；首次提交允许未签名，已有签名发布记录的后续提交需要使用登记密钥。具体资料见 [正式提交所需资料](OPEN_QUESTIONS.md) 和 [AppHub 发布准备](APPHUB_PUBLISHING.md)。
