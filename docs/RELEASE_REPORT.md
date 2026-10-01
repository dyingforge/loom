# 20 发布准备报告

报告日期：2026-10-01。结论分别记录“本地包检查”（机器可复现）与“获准上架”（需人工提交后由 App Hub 评审）两个状态。

## 本地包检查（可在本仓库复现）

| 项 | 状态 | 证据 |
| --- | --- | --- |
| `bundle/` 目录完整 | ✓ | `bundle/manifest.json`、`bundle/listing.json`、`bundle/main.splash`、`bundle/assets/icon.svg`、`bundle/screenshots/`（待补真实截图） |
| `integrity.bundle_blake3` 留空 | ✓ | `manifest.json` 该字段为空，由 `hub stamp` 在提交前填写 |
| 无密钥、令牌、登录表单 | ✓ | `grep -rE "(MINIMAX_API_KEY\|api[_-]?key\|secret\|password\|token)" bundle/` 无命中 |
| 网络主机已声明 | ✓ | `manifest.json` `network.hosts = ["loom.example.com"]`；提交前需替换为真实公网域名 |
| capabilities 最小化 | ✓ | 仅声明 `storage` 与 `net`；无 `images`、`web`、`camera` 等 |
| 客户端 main.splash 按 SCRIPT-API.md 编写 | ✓ | 411 行；声明、fn、根 widget 结构符合 §"Shape of a program"；通过 `start_timeout` 注入 UI |
| 隐私说明 | ✓ | `docs/PRIVACY.md`，含接收方清单、用户文本可能被注入的限制 |
| 架构决策文档化 | ✓ | `docs/DECISIONS.md`（D1–D13） |
| 依赖守卫通过 | ✓ | `server/tests/test_architecture.py` 三项断言；CI 必跑 |
| 全部测试通过 | ✓ | `pytest server/tests/ client/tests/` → 96 passed, 3 skipped（真实模型集成测试需 `MINIMAX_API_KEY`） |
| 真实模型端到端 | ✓ | `pytest server/tests/test_minimax_integration.py` 在含 `MINIMAX_API_KEY` 环境 → 3 passed |
| 服务端独立部署 | ✓ | `server/` 不进入 `bundle/`；通过 `scripts/run_dev_server.py` 启动 |
| 限流与评审额度 | ✓ | `server/tests/test_rate_limit.py` 覆盖 IP 限流、评审 token、每日费用上限 |
| 九场景回归 | ✓ | `server/tests/test_scenarios.py` 9 项全过 |

## 未能在本环境复现（需要 OctoScript 运行时）

- `hub stamp` / `hub check` / `hub scan` / `hub sign-manifest`：未安装 `hub` 二进制；命令本身在 `OctoSense-App-Hub` 仓库发布流水线中。
- `tools/octo run` / `tools/octo shot` 真实截图：本环境未克隆 `OctoScript-App-Design-Flow` 也未构建 `card-host`。
- `bundle/screenshots/01-main.png`：缺失；待用户在能联网的 OctoSense 设备完成 `tools/setup-native.py` 构建后捕获。
- 真实运行的录屏：缺失；待用户在 demo 环境下录制。

## 待人工完成

按 PUBLISHING.md §3 的检查清单：

1. 把 `loom.example.com` 替换为真实部署域名；
2. 完整跑 `tools/octo check "$B"` 与 `hub check "$B" --allow-unsigned`，确认无 `[refused]`；
3. 跑 `hub scan "$B" --packet "$APP/build/review.json"`，填写七问；
4. 由发布者创建私钥并 `hub sign-manifest`；
5. 提交 PR 至 `OctoSense-App-Hub`（参照 PUBLISHING.md §3.8）。

## 演示备份与失败兜底

按 PRD §3.5：演示当天若 API 失败，按如下顺序兜底：

1. 先如实展示失败（HTTP 状态、错误原因）；
2. 播放 issue 19 已录制的真实运行录屏；
3. 演示 fallback 数据（手工准备的固定方案），明确说明这不是模型输出。

注：本票不包含录屏录制本身；该项在用户具备演示设备后补做。

## 与 issues/20-release-materials.md 的对应

| 任务 | 状态 |
| --- | --- |
| 重新核对发布规则 | 已做（见 .scratch/octoscript-agents.md 与 .scratch/publishing.md） |
| 声明 storage、net、host | 已做 |
| 服务端独立部署 | 已做（server/ 不打包） |
| 包内无密钥 | 已验证（grep 无命中） |
| 隐私说明 | 已写（docs/PRIVACY.md） |
| 真实环境截图与录屏 | 未做（缺 OctoScript 运行时） |
| 演示失败兜底 | 已写（本文件） |
| 本票不自动上架 | ✓（无提交动作） |
