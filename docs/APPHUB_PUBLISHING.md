# Loom 的 AppHub 发布准备

核查日期：2026-10-12。核查对象为当前 `bundle/`、项目发布文档、AppHub 官方发布要求及官方应用运行代码。

## 发布内容与提交入口

AppHub 接收 `bundle/` 中的 Splash 程序、清单、图标、字体和真实截图。客户端零服务化，清单只声明 `storage` 与 `model`，没有需要独立运行的服务。现有 GitHub 仓库 `dyingforge/loom` 已公开，Issues 页面可以访问。

提交方式是把最终应用包提交到公开仓库、创建版本标签，再到 OctoSense-App-Hub 仓库创建标题为 `Submit loom.pm-calendar <version>` 的 Issue。维护者审核指定提交中的应用包，并负责发布。要求见[官方发布文档](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/PUBLISHING.md#submitting)。

## 当前核查结果

| 检查项目 | 结果 | 发布前需要完成的工作 |
| --- | --- | --- |
| 应用身份 | `loom.pm-calendar`，版本 `0.1.1` | 在最终提交前重新核查目录中的版本记录 |
| 应用包检查 | 本次 `hub check --allow-unsigned --catalog` 通过；首次提交选择 `unsigned` | 提交前用当前官方工具复查最终文件 |
| 目录检查 | 下载的官方目录 sequence 为 4；带目录的检查通过 | 提交前重新下载并验证目录 |
| 权限 | `storage`、`model`，存储额度 4 MiB，`agent: null`，不声明网络 | 已完成，无额外授权需要核对 |
| 图标与截图 | 清单引用的文件存在，应用包磁盘占用约 4.4 MiB | 在发布目标环境重新验证真实操作和截图 |
| 业务存储 | 客户端使用官方 `fs` 在应用目录交替写入 `state-a.json`/`state-b.json` 快照 | 已完成，不需要宿主额外能力 |
| 启动时区 | 客户端固定东八区（UTC+8），不读取设备时间文件 | 已完成 |
| 公网服务 | 客户端不声明网络，没有自有服务端 | 已完成，提交后无需保持任何进程运行 |
| 发布资料 | 清单已有名称 `dyingforge`、支持链接 `https://github.com/dyingforge/loom/issues` 和隐私链接 `https://github.com/dyingforge/loom/blob/v0.1.1/docs/PRIVACY.md` | 已完成 |
| 审核资料 | 七项审核问题已逐项回答 | 已完成，见[审核回答](APPHUB_SUBMISSION.md) |

当前核查使用 `native/LOCK.json` 固定的官方 OctoSense-App-Hub 提交 `655114c4943cd2490daaefa2173e7b5aaa20669f` 构建的 `hub` 与 `card-host`；官方 `hub check`、真实文件存储、演示闭环、向量核验与客户端状态检查均已通过。真实模式已于 2026-10-12 在 OctoSense 桌面 RC4 与用户自配模型提供方下完成安装运行验证，证据见 `review/ANSWERS.md`。

## 官方宿主兼容性

### 业务存储

`bundle/main.splash` 使用官方 `fs` 文件能力，在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整快照，不依赖自定义宿主服务。当前发布包针对官方 AppHub 提交 `655114c4943cd2490daaefa2173e7b5aaa20669f` 构建和验证，不需要宿主提供额外业务存储能力。

`native/LOCK.json` 固定官方 OctoSense-App-Hub 提交及其 `Cargo.toml` 引用的 Makepad 与 Octoscript；项目不带私有原生补丁。应用包不能安装原生运行代码；涉及新增运行能力的要求见[官方开发指南](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/DEVELOPMENT.md#choose-the-appropriate-delivery-path)。

### 首次启动与设备时区

客户端固定东八区（UTC+8），不读取或生成设备时间文件，AppHub 安装后的启动过程不需要本项目的 Python 启动脚本。官方宿主对空白应用数据目录的首次启动会初始化 `state-a.json`，并显示东八区当前日期与七天后的初始截止日期。

## 发布资料和验证

清单已确定发布者 `dyingforge`、支持入口 `https://github.com/dyingforge/loom/issues` 与隐私入口 `https://github.com/dyingforge/loom/blob/v0.1.1/docs/PRIVACY.md`。现有清单声明 `macos`；发布资料只声明真实验证的平台。

按最终发布环境运行目标生成、文字修改、确认核验、正式与候选计划切换、重新启动恢复与失败重试流程；客户端演示模式可覆盖全部链路，真实模式需要宿主接入模型提供方。截图来自该应用的真实运行状态。官方要求图标和至少一张截图，截图数量最多八张；具体要求见[发布流程](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/PUBLISHING.md)。

七项审核问题的回答保存在[审核回答](APPHUB_SUBMISSION.md)；最终版本提交前用当前官方工具重新生成审核资料。

## 最终检查、签名与提交

全部文件和截图确定后，按顺序运行检查。`LOOM_HUB_BIN` 指向发布时准备的官方 `hub`；`LOOM_HUB_CATALOG` 指向重新下载的官方目录：

```sh
"$LOOM_HUB_BIN" stamp bundle
"$LOOM_HUB_BIN" check bundle --allow-unsigned --catalog "$LOOM_HUB_CATALOG"
"$LOOM_HUB_BIN" scan bundle --packet .scratch/apphub-release/review.json
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
- 实际验证的平台、官方宿主版本与操作流程。

维护者完成审核与发布后，以其给出的 catalog sequence 确认上架，并在正式客户端验证安装、打开和重新启动。

## 当前检查证据

检查输出：

```text
loom.pm-calendar 0.1.1 — PASSED
  [warning] publisher-signature: unsigned: accountability rests on the hub alone
  grants: capabilities {"model", "storage"}, hosts {}, storage 4194304 bytes, agent none
```

带目录的检查退出状态为 0。七项审核问题的回答保存在[审核回答](APPHUB_SUBMISSION.md)，最终提交前用当前官方工具重新运行 `hub scan` 和 `hub check`。首次提交未签名：`v0.1.1` 标签已创建并推送（commit `9522189afc1b63cb488b075adb96eca1d242346f`），发布 workflow 运行成功，发布包经本地 `publisher-unpack`/`publisher-verify` 验证通过，提交 Issue 为 [OctoSense-App-Hub #220](https://github.com/OctoSense-org/OctoSense-App-Hub/issues/220)。

中间资料保存在 Git 忽略的 `.scratch/`，包括官方文档、目录、检查输出、审核回答与真实客户端证据。
