# Loom 客户端 ↔ 服务端协议

依据实施计划 1.3「双实现、单向量」与 1.4 数据模型，定义客户端 Splash 与 Python 服务端之间的 JSON 契约。客户端不直接依赖 Pydantic，按本文件实现解析。

## 公共约定

- 时间统一使用 ISO 8601 字符串；客户端按设备本地时间约定；首版不处理时区与夏令时。
- 整数版本号 `version` 自 1 起；写入时调用方负责递增；服务端校验时若快照版本与方案 `baseVersion` 不符，要求重新规划。
- `restDays` 使用 Python `datetime.weekday()` 约定：`0=周一 … 6=周日`。
- 所有 ID 为调用方生成的非空字符串。

## 项目

```json
{
  "id": "loom-current",
  "version": 1,
  "goal": "在 5 天内完成原型实现并联调",
  "deadline": "2026-10-08T00:00:00",
  "milestones": [
    {"id": "m1", "title": "原型演示", "due": "2026-10-08T18:00:00"}
  ],
  "tasks": [
    {
      "id": "t1", "title": "领域模型与校验器",
      "priority": 1, "remainingHours": 6, "done": false,
      "dependsOn": [], "adjustable": true,
      "blocks": [
        {"id": "t1-b1", "taskId": "t1",
         "start": "2026-10-02T09:00:00", "end": "2026-10-02T15:00:00",
         "done": false}
      ]
    }
  ],
  "fixedEvents": [
    {"id": "f1", "title": "周会",
     "start": "2026-10-02T13:00:00", "end": "2026-10-02T14:00:00"}
  ],
  "workHours": {"start": "09:00", "end": "18:00"},
  "restDays": [5, 6],
  "preferences": "上午做需要专注的任务",
  "autoAdjust": true
}
```

## 推进 Agent

请求：

```http
POST /v1/agent/advance
Content-Type: application/json

{
  "snapshot": { /* 上面的 Project 对象 */ },
  "trigger": "new" | "delay" | "progress" | "resume" | "propose",
  "clarificationAnswer": "（可选）",
  "state": { /* 可选；恢复暂停轮次 */ }
}
```

响应：

```json
{
  "type": "plan" | "clarify" | "failed",
  "payload": {
    "planId": "plan-2",
    "baseVersion": 1,
    "changes": [{"blockId": "...", "before": null|"Block", "after": null|"Block"}],
    "risks": [], "exceptions": [], "rationale": ""
  },
  "trace": [{"type":"decision","kind":"tool"}, ...],
  "state": {"/* 暂停可序列化；含 llm_calls、invalid_streak、status 等 */"}
}
```

`type=clarify` 时 `payload = {"question": "..."}`；`type=failed` 时 `payload = {"reason": "..."}`。

## 核验执行

```http
POST /v1/agent/verify
{
  "planId": "plan-2",
  "versionBefore": 1,
  "versionAfter": 2,
  "readbackSnapshot": { /* Project */ }
}
```

响应：`{"status": "verified" | "not_verified", "reason": "..."}`。

## 客户端持久化

- 单一快照写入：`snap-a.json` / `snap-b.json` 交替；
- 每份 body：`{"sequence": int, "checksum": "sha256", "snapshot": { ... }}`；
- 校验与回读算法见 `client/store.py`，对应 Splash 实现见 `client/main.splash` 中 `save_snapshot_to` / `load_latest_snapshot`。

## 网络声明

`bundle/manifest.json` 必须包含 `network.hosts` 中的服务端域名；本计划示例为 `loom.example.com`，正式提交时按部署平台修改。
