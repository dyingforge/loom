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
| 业务存储 | 客户端使用官方 `fs` 在应用目录交替写入 `state-a.json`/`state-b.json` 快照 | 已完成，不需要宿主额外能力 |
| 启动时区 | 客户端固定东八区（UTC+8），不读取设备时间文件 | 已完成 |
| 公网服务 | 客户端当前使用 Cloudflare 临时隧道地址 | 配置持续运行的正式 HTTPS 服务 |
| 发布资料 | 清单已有名称、支持链接和隐私链接 | 发布者确认身份及正式隐私内容 |
| 审核资料 | 已生成 `hub scan` 的七项审核问题 | 对最终应用包逐项提供回答和证据 |

本次检查使用主项目已有的 `hub`，其构建记录指向 AppHub 修复提交 `3599b69909898a76cbc454077ef552dc543ddeb4`。本次没有构建最新官方工具，也没有完成官方桌面客户端中的安装与运行验证。

## 官方宿主兼容性

### 业务存储

`bundle/main.splash` 使用官方 `fs` 文件能力，在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整快照，不依赖自定义宿主服务。当前发布包针对官方 AppHub 提交 `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1` 构建和验证，不需要宿主提供额外业务存储能力。

`native/LOCK.json` 固定官方 OctoSense-App-Hub 提交及其 `Cargo.toml` 引用的 Makepad 与 Octoscript；项目不带私有原生补丁。应用包不能安装原生运行代码；涉及新增运行能力的要求见[官方开发指南](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/DEVELOPMENT.md#choose-the-appropriate-delivery-path)。

### 首次启动与设备时区

客户端固定东八区（UTC+8），不再读取或生成设备时间文件，AppHub 安装后的启动过程不需要本项目的 Python 启动脚本。官方宿主对空白应用数据目录的首次启动会初始化 `state-a.json`，并显示东八区当前日期与七天后的初始截止日期。

## 正式服务部署

准备持续运行的 HTTPS 地址和带持久磁盘的服务环境。部署内容包括 `server/`、`requirements.txt` 和供 `/privacy` 使用的 `docs/PRIVACY.md`。

- 服务端环境保存 `MINIMAX_API_KEY`、模型配置、额度和限流参数；应用包只包含正式服务地址。
- HTTPS 反向代理转发到 Uvicorn；使用单个 Uvicorn 工作进程。现有规划任务保存在进程内存中，创建任务与查询任务必须到达同一进程。服务内部已经配置四个线程处理规划。
- `LOOM_USAGE_DB` 指向持久磁盘上的 SQLite 文件，保留使用额度和暂停对话。配置服务自动启动、异常终止后重新启动以及数据库备份。
- 核查代理后的真实访问者 IP。限流使用 `connection.client.host`，代理配置需要让该字段对应真实访问者，并仅信任受控代理提供的请求头。
- 按实际运营预算设置公共每日额度、评审额度和请求频率。本项目客户端当前未发送 `x-loom-reviewer-token`；评审专用额度的使用需要单独验证。
- 验证 `/healthz`、`/privacy`、真实目标生成、文字修改和保存核验。服务重新启动会终止内存中的规划过程，客户端需要正确显示该结果。

当前 Cloudflare 临时隧道的 `/healthz` 与 `/privacy` 已验证返回 200，真实客户端通过该地址完成目标生成、修改、确认与重新确认。临时隧道不是永久服务，正式提交需要持续运行的地址。

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
