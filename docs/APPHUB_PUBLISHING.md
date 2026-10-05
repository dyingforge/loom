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
| 权限 | `storage`、`net`，存储额度 4 MiB，`agent: null` | 服务域名与实际请求保持一致 |
| 图标与截图 | 清单引用的文件存在，应用包磁盘占用约 4.4 MiB | 在发布目标环境重新验证真实操作和截图 |
| 业务存储 | 客户端使用官方 `fs` 在应用目录交替写入 `state-a.json`/`state-b.json` 快照 | 已完成，不需要宿主额外能力 |
| 启动时区 | 客户端固定东八区（UTC+8），不读取设备时间文件 | 已完成 |
| 公网服务 | 客户端当前使用 Cloudflare 临时隧道地址 | 保持临时隧道运行；隧道地址变化时同步更新 |
| 发布资料 | 清单已有名称 `dyingforge`、支持链接 `https://github.com/dyingforge/loom/issues` 和隐私链接 `https://github.com/dyingforge/loom/blob/v0.1.0/docs/PRIVACY.md` | 已完成 |
| 审核资料 | 七项审核问题已逐项回答 | 已完成，见[审核回答](APPHUB_SUBMISSION.md) |

当前核查使用 `native/LOCK.json` 固定的官方 OctoSense-App-Hub 提交 `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1` 构建的 `hub` 与 `card-host`；官方 `hub check`、真实文件存储、真实客户端模型流程与服务检查均已通过。尚未在官方桌面客户端中完成安装与运行验证。

## 官方宿主兼容性

### 业务存储

`bundle/main.splash` 使用官方 `fs` 文件能力，在应用目录交替写入 `state-a.json` 与 `state-b.json` 两份完整快照，不依赖自定义宿主服务。当前发布包针对官方 AppHub 提交 `0d5b47a2ae9eb98020feca26b7c895a3cf797dc1` 构建和验证，不需要宿主提供额外业务存储能力。

`native/LOCK.json` 固定官方 OctoSense-App-Hub 提交及其 `Cargo.toml` 引用的 Makepad 与 Octoscript；项目不带私有原生补丁。应用包不能安装原生运行代码；涉及新增运行能力的要求见[官方开发指南](https://github.com/OctoSense-org/OctoSense-App-Hub/blob/main/docs/DEVELOPMENT.md#choose-the-appropriate-delivery-path)。

### 首次启动与设备时区

客户端固定东八区（UTC+8），不再读取或生成设备时间文件，AppHub 安装后的启动过程不需要本项目的 Python 启动脚本。官方宿主对空白应用数据目录的首次启动会初始化 `state-a.json`，并显示东八区当前日期与七天后的初始截止日期。

## 服务与隧道

提交方案使用本机单个 Uvicorn 进程与 Cloudflare 临时 HTTPS 隧道。部署内容包括 `server/`、`requirements.txt` 和供 `/privacy` 使用的 `docs/PRIVACY.md`。

- 服务端通过 `LOOM_ENV_FILE` 加载环境文件中的 `MINIMAX_API_KEY`；应用包只包含实际服务地址。
- 使用单个 Uvicorn 工作进程。现有规划任务保存在进程内存中，创建任务与查询任务必须到达同一进程。服务内部已经配置四个线程处理规划。
- `LOOM_USAGE_DB` 指向被忽略数据目录中的 SQLite 文件，保留使用额度和暂停对话。
- 公共每日额度与请求频率按实际运营预算设置，当前为每日 1000 美分与每 IP 每分钟 60 次。
- 验证 `/healthz`、`/privacy`、真实目标生成、文字修改和保存核验。服务重新启动会终止内存中的规划过程，客户端需要正确显示该结果。

当前 Cloudflare 临时隧道的 `/healthz` 与 `/privacy` 已验证返回 200，真实客户端通过该地址完成目标生成、修改、确认与重新确认。提交期间需要保持本机服务与隧道运行；隧道地址变化时同步更新 `bundle/main.splash` 的 `api_origin`、`bundle/manifest.json` 的 `network.hosts` 与相关文档。

## 发布资料和验证

清单已确定发布者 `dyingforge`、支持入口 `https://github.com/dyingforge/loom/issues` 与隐私入口 `https://github.com/dyingforge/loom/blob/v0.1.0/docs/PRIVACY.md`。现有清单声明 `macos`；发布资料只声明真实验证的平台。

按最终发布环境运行目标生成、文字修改、确认核验、正式与候选计划切换、重新启动恢复、网络失败和额度耗尽流程。截图来自该应用的真实运行状态。官方要求图标和至少一张截图，截图数量最多八张；具体要求见[发布流程](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/PUBLISHING.md)。

七项审核问题的回答保存在[审核回答](APPHUB_SUBMISSION.md)；最终版本提交前用当前官方工具重新生成审核资料。

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

## 当前检查证据

检查输出：

```text
loom.pm-calendar 0.1.0 — PASSED
  [warning] publisher-signature: unsigned: accountability rests on the hub alone
  grants: capabilities {"net", "storage"}, hosts {"tariff-boards-bradley-theory.trycloudflare.com"}, storage 4194304 bytes, agent none
```

带目录的检查退出状态为 0。七项审核问题的回答保存在[审核回答](APPHUB_SUBMISSION.md)，最终提交前用当前官方工具重新运行 `hub scan` 和 `hub check`。尚未创建发布者密钥、版本标签或提交 Issue。

中间资料保存在 Git 忽略的 `.scratch/`，包括官方文档、目录、检查输出、审核回答与真实客户端证据。
