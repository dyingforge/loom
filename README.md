# Loom

Loom 是使用 OctoScript 原生控件的目标日历，零服务化自包含。填写目标和截止日期后，客户端通过宿主 `model.complete` 拆分任务并安排到真实月历；宿主没有模型服务时自动使用内置演示数据。用户查看每日安排，通过文字建议修改计划，确认并完成本地核验。

## 构建并启动客户端

原生宿主由 `native/LOCK.json` 固定的依赖源码构建。首次使用或依赖更新后运行：

```sh
python3 scripts/build_native.py
```

脚本在被 Git 忽略的 `.scratch/native` 中检出官方提交，执行 `cargo build --release --locked` 构建 `hub` 和 `card-host`，并在二进制旁写入构建标记。只检查锁定记录与现有源码而不构建时运行：

```sh
python3 scripts/build_native.py --verify
```

构建完成后打开应用：

```sh
python3 scripts/run_client.py
```

`run_client.py` 会核对构建标记，未按锁定来源构建的旧原生宿主会被拒绝。客户端通过宿主能力 `storage` 与 `model` 工作，不声明网络，也不向任何自有服务端发送请求。

## 演示与验证

[演示说明](docs/DEMO.md) 记录具体操作、运行环境和使用限制。

```sh
python3 scripts/check_demo.py
python3 scripts/check_client_state.py
.scratch/native/OctoSense-App-Hub/target/release/hub check bundle --allow-unsigned
```

`scripts/check_demo.py` 驱动演示闭环（生成→确认→核验→保存→月历→修改→追问→重启恢复）；`scripts/check_client_state.py` 检查草稿保存与重启恢复；`hub check` 是发布门禁。客户端固定东八区（UTC+8），业务记录保存在应用目录的 `state-a.json` 与 `state-b.json` 两份交替快照中，没有服务端数据库。

## 代码与资料

- `bundle/main.splash`：目标入口、真实月历、当天完整安排、计划说明、`model.complete` 规划通道与演示模式。
- `bundle/assets/fonts/`：Noto Sans SC 与 Manrope 字体。每个字体的 name table 内嵌完整 OFL 1.1 授权，原始授权文本保存在 `docs/licenses/`。
- `docs/PROTOCOL.md`：客户端协议，含状态文件、`model.complete` 契约与各阶段 Schema、约束语义、演示模式与拒绝码。
- `review/ANSWERS.md`：演示数据出处与真实模式验证证据。
- `vectors/`：日历约束的共用验证数据。
- `server/`：旧版服务端实现的参考资产，客户端不再使用。
- `CONTEXT.md`、`constraints.md`：领域词汇与约束。

项目面向单用户、单设备和应用内日历。实施进度记录在 [实施进度](docs/PROGRESS.md)。

## License

代码与文档采用 Apache-2.0，全文见仓库根目录 `LICENSE`。字体各按其自身授权：Noto Sans SC 与 Manrope 均为 SIL Open Font License 1.1，授权全文内嵌在字体的 name table 中，原始授权文本保存在 `docs/licenses/`。
