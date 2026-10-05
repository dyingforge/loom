# Loom 的 AppHub 发布准备

核查日期：2026-10-05。核查对象为当前 `bundle/`、项目发布文档、AppHub 官方发布要求及官方应用运行代码。

## 发布内容与提交入口

AppHub 接收 `bundle/` 中的 Splash 程序、清单、图标、字体和真实截图。Python 服务需要独立运行。现有 GitHub 仓库 `dyingforge/loom` 已公开，Issues 页面可以访问。

提交方式是把最终应用包提交到公开仓库、创建版本标签，再到 OctoSense-App-Hub 仓库创建标题为 `Submit loom.pm-calendar <version>` 的 Issue。维护者审核指定提交中的应用包，并负责发布。要求见[官方发布文档](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/PUBLISHING.md#submitting)。

## 当前核查结果

| 检查项目 | 结果 | 发布前需要完成的工作 |
| --- | --- | --- |
| 应用身份 | `loom.pm-calendar`，版本 `0.1.0` | 在最终提交前重新核查目录中的版本记录 |
| 应用包检查 | 现有 `hub check` 通过；只有未签名提示 | 使用提交时的官方检查工具复查最终文件 |
| 目录检查 | 下载的官方目录 sequence 为 4；带目录的检查通过 | 提交前重新下载并验证目录 |
| 权限 | `storage`、`net`，存储额度 4 MiB，`agent: null` | 正式服务域名与实际请求保持一致 |
| 图标与截图 | 清单引用的文件存在，应用包磁盘占用约 4.4 MiB | 在发布目标环境重新验证真实操作和截图 |
| 业务存储 | 客户端调用 `{{state}}/v1/state`、`/v1/draft`、`/v1/commit` | 官方宿主需要提供经过审核的对应能力 |
| 启动时区 | `boot()` 读取由 `run_client.py` 写入的 `device.json` | 商店启动路径需要提供设备时间配置 |
| 公网服务 | 客户端仍使用 `trycloudflare.com` 临时地址 | 配置持续运行的正式 HTTPS 服务 |
| 发布资料 | 清单已有名称、支持链接和隐私链接 | 发布者确认身份及正式隐私内容 |
| 审核资料 | 已生成 `hub scan` 的七项审核问题 | 对最终应用包逐项提供回答和证据 |

本次检查使用主项目已有的 `hub`，其构建记录指向 AppHub 修复提交 `3599b69909898a76cbc454077ef552dc543ddeb4`。本次没有构建最新官方工具，也没有完成官方桌面客户端中的安装与运行验证。

## 官方宿主兼容性

### 业务存储服务

`bundle/main.splash` 使用 `state_origin = "{{state}}"`。`native/patches/app-hub-state.patch` 为 `card-host` 添加了 SQLite 服务、主机许可和占位符替换。

核查时，官方 AppHub `main` 提交为 `9e7f0778429125402dcfefef95ba2b01e8de7b94`；官方 OctoSense `main` 提交为 `d9d3b8be67614d894ccc685bebb3234a8e467193`，其 Cargo 配置固定 AppHub 为 `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1`。

这两个 AppHub 版本的商店应用运行代码均未提供 Loom 使用的业务存储服务。当前官方入口处理只替换 `{{assets}}`。依据为[官方商店应用运行代码](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/9e7f0778429125402dcfefef95ba2b01e8de7b94/crates/appstore/src/cardapp.rs)和[脚本入口代码](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/9e7f0778429125402dcfefef95ba2b01e8de7b94/crates/app-contract/src/entry.rs)。

发布准备需要把业务存储能力提交给上游维护者审核，并接入正式商店应用运行路径。随后验证目标 OctoSense 版本已经包含该能力。仅构建项目自己的 `card-host` 无法给其他安装者增加这项能力。

`native/LOCK.json` 固定的 Makepad 内存管理、终止处理和诊断补丁也需要在正式宿主版本上核查。应用包无法安装原生运行代码；涉及新增运行能力的要求见[官方开发指南](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/DEVELOPMENT.md#choose-the-appropriate-delivery-path)。

### 首次启动与设备时区

`scripts/run_client.py` 在启动前把设备时区和 UTC 偏移写入应用数据目录的 `device.json`。`bundle/main.splash` 第 447 行直接读取该文件。AppHub 安装后的启动过程不会执行本项目的 Python 启动脚本。

本次使用空白应用数据目录、现有修复版 `card-host` 和隐藏窗口直接运行真实应用，日志显示：

```text
card-host: loom.pm-calendar 0.1.0 admitted
splash:4911337984:451:26 - file not found
```

错误发生在读取 `device.json` 的位置。测试实例已通过 `/quit` 关闭。发布目标宿主需要提供正式的设备时间配置，客户端从该配置完成首次初始化。发布验收必须覆盖空白安装、重新启动以及设备时区变化。

## 正式服务部署

准备持续运行的 HTTPS 地址和带持久磁盘的服务环境。部署内容包括 `server/`、`requirements.txt` 和供 `/privacy` 使用的 `docs/PRIVACY.md`。

- 服务端环境保存 `MINIMAX_API_KEY`、模型配置、额度和限流参数；应用包只包含正式服务地址。
- HTTPS 反向代理转发到 Uvicorn；使用单个 Uvicorn 工作进程。现有规划任务保存在进程内存中，创建任务与查询任务必须到达同一进程。服务内部已经配置四个线程处理规划。
- `LOOM_USAGE_DB` 指向持久磁盘上的 SQLite 文件，保留使用额度和暂停对话。配置服务自动启动、异常终止后重新启动以及数据库备份。
- 核查代理后的真实访问者 IP。限流使用 `connection.client.host`，代理配置需要让该字段对应真实访问者，并仅信任受控代理提供的请求头。
- 按实际运营预算设置公共每日额度、评审额度和请求频率。本项目客户端当前未发送 `x-loom-reviewer-token`；评审专用额度的使用需要单独验证。
- 验证 `/healthz`、`/privacy`、真实目标生成、文字修改和保存核验。服务重新启动会终止内存中的规划过程，客户端需要正确显示该结果。

本次访问当前临时域名的 `/healthz` 和 `/privacy` 均未完成 TLS 连接，返回 HTTP 000。这项结果说明本次未验证该地址可用。

正式域名确定后，更新 `bundle/main.splash` 的 `api_origin`、`bundle/manifest.json` 的 `network.hosts`、`bundle/listing.json` 的 `publisher.privacy_policy_url`。更新隐私说明中的实际数据处理、保留期限、删除方式和联系方式，并更新演示说明。

## 发布资料和验证

发布者确认清单中的显示名称、支持联系方式、隐私内容和稳定的 publisher id。现有清单声明 `macos`；发布资料只声明真实验证的平台。

按最终发布环境运行目标生成、文字修改、确认核验、正式与候选计划切换、重新启动恢复、网络失败和额度耗尽流程。截图来自该应用的真实运行状态。官方要求图标和至少一张截图，截图数量最多八张；具体要求见[发布流程](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/PUBLISHING.md)。

本次生成的审核问题文件为 `.scratch/apphub-research/review.json`。最终版本需要重新生成审核资料，并回答功能与描述、平台与类别、权限与主机用途、界面真实性、面向助手的指令、文字内容以及审核建议七项问题。

## 最终检查、签名与提交

全部文件和截图确定后，按顺序运行检查。`LOOM_HUB_BIN` 指向发布时准备的官方 `hub`；`LOOM_HUB_CATALOG` 指向重新下载的官方目录：

```sh
"$LOOM_HUB_BIN" stamp bundle
"$LOOM_HUB_BIN" check bundle --allow-unsigned --catalog "$LOOM_HUB_CATALOG"
"$LOOM_HUB_BIN" scan bundle --packet .scratch/apphub-research/final-review.json
```

官方允许首次提交使用未签名应用包。已有签名发布记录的发布者，其后续版本和同一发布者的新应用需要使用已记录的密钥。签名规则见[官方签名要求](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/PUBLISHING.md#signing)。签名发布时，在文件确定后运行：

```sh
"$LOOM_HUB_BIN" sign-manifest bundle --key "$LOOM_SIGNING_KEY" --key-id "$LOOM_PUBLISHER_ID"
"$LOOM_HUB_BIN" check bundle --catalog "$LOOM_HUB_CATALOG" --publisher-key "$LOOM_PUBLISHER_ID=$LOOM_PUBLISHER_PUBLIC_KEY"
```

私钥保存在仓库外并备份。签名后修改任何应用包文件，都需要重新计算摘要、签名和检查。使用未签名开发副本完成 `card-host` 验证。

将最终文件提交并推送到公开仓库，创建与版本一致的标签。提交 Issue 中填写：

- 仓库地址、版本标签和完整 commit SHA。
- 应用包路径 `bundle/`。
- publisher id 和公钥；首次未签名提交注明 `unsigned`。
- 指定提交的完整 `hub check` 输出和七项审核问题的回答。
- 实际验证的平台、官方宿主版本、操作流程和服务地址。

维护者完成审核与发布后，以其给出的 catalog sequence 确认上架，并在正式客户端验证安装、打开和重新启动。

## 本次检查证据

检查输出：

```text
loom.pm-calendar 0.1.0 — PASSED
  [warning] publisher-signature: unsigned: accountability rests on the hub alone
  grants: capabilities {"net", "storage"}, hosts {"quotes-geographical-per-foreign.trycloudflare.com"}, storage 4194304 bytes, agent none
```

带目录的检查退出状态为 0。`hub scan` 成功生成七项审核问题，没有调用外部审核者。本次未创建发布者密钥、版本标签或提交 Issue。

中间资料保存在 Git 忽略的 `.scratch/apphub-research/`，包括官方文档、源码、目录、检查输出、审核问题和首次启动日志。
