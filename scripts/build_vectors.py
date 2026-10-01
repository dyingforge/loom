"""生成 `vectors/` 下的所有 C1–C7 验证向量。

每条约束至少 2 个反例 + 1 个正例，外加若干组合场景。生成的结果可被
服务端与客户端共用测试加载。运行：`python3 scripts/build_vectors.py`。
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path("vectors")
OUT.mkdir(exist_ok=True)


# Python weekday(): 0=周一 ... 6=周日
# 工作日 2026-10-02 是周五，2026-10-03 是周六(weekday=5)
BASE_PROJECT = {
    "id": "p", "version": 1, "goal": "g", "deadline": None,
    "milestones": [],
    "fixedEvents": [],
    "workHours": {"start": "09:00", "end": "18:00"},
    "restDays": [5, 6],  # 周六、周日（Python weekday 约定）
    "preferences": "", "autoAdjust": True,
}


def write(name: str, payload: dict) -> None:
    (OUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def project_with(tasks: list[dict], fixed: list[dict] | None = None,
                 rest_days: list[int] | None = None,
                 work_hours: dict | None = None) -> dict:
    p = json.loads(json.dumps(BASE_PROJECT))
    p["tasks"] = tasks
    if fixed:
        p["fixedEvents"] = fixed
    if rest_days is not None:
        p["restDays"] = rest_days
    if work_hours:
        p["workHours"] = work_hours
    return p


# ---------- C1 ----------
write("c1_done_blocks.json", {
    "positive": [
        {
            "name": "不对已完成任务排程",
            "project": project_with([
                {"id": "t1", "title": "已完成", "priority": 1, "remainingHours": 0,
                 "done": True, "dependsOn": [], "adjustable": True,
                 "blocks": [{"id": "b1", "taskId": "t1",
                             "start": "2026-10-02T10:00", "end": "2026-10-02T12:00",
                             "done": True}]},
                {"id": "t2", "title": "未开始", "priority": 1, "remainingHours": 4,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t2", "start": "2026-10-02T09:00", "end": "2026-10-02T13:00"}
            ]},
        }
    ],
    "negative": [
        {
            "name": "对已完成任务再排",
            "project": project_with([{
                "id": "t1", "title": "已完成", "priority": 1, "remainingHours": 0,
                "done": True, "dependsOn": [], "adjustable": True, "blocks": []
            }]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T10:00", "end": "2026-10-02T11:00"}
            ]},
            "expected_codes": ["C1"],
        },
        {
            "name": "移动已存在的已完成块",
            "project": project_with([{
                "id": "t1", "title": "进行中", "priority": 1, "remainingHours": 1,
                "done": False, "dependsOn": [], "adjustable": True,
                "blocks": [{"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T10:00", "end": "2026-10-02T12:00",
                            "done": True}]
            }]),
            "candidate": {"blocks": [
                {"id": "b1", "taskId": "t1",
                 "start": "2026-10-02T11:00", "end": "2026-10-02T13:00"}
            ]},
            "expected_codes": ["C1"],
        },
    ],
})


# ---------- C2 ----------
write("c2_fixed_events.json", {
    "positive": [
        {
            "name": "块不与固定日程重叠",
            "project": project_with(
                tasks=[{"id": "t1", "title": "t", "priority": 1,
                        "remainingHours": 2, "done": False, "dependsOn": [],
                        "adjustable": True, "blocks": []}],
                fixed=[{"id": "f1", "title": "会议", "start": "2026-10-02T13:00",
                        "end": "2026-10-02T14:00"}],
            ),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T15:00", "end": "2026-10-02T17:00"}
            ]},
        },
    ],
    "negative": [
        {
            "name": "块起点在固定日程内",
            "project": project_with(
                tasks=[{"id": "t1", "title": "t", "priority": 1,
                        "remainingHours": 2, "done": False, "dependsOn": [],
                        "adjustable": True, "blocks": []}],
                fixed=[{"id": "f1", "title": "会议", "start": "2026-10-02T13:00",
                        "end": "2026-10-02T14:00"}],
            ),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T13:30", "end": "2026-10-02T15:30"}
            ]},
            "expected_codes": ["C2"],
        },
        {
            "name": "块包含整个固定日程",
            "project": project_with(
                tasks=[{"id": "t1", "title": "t", "priority": 1,
                        "remainingHours": 4, "done": False, "dependsOn": [],
                        "adjustable": True, "blocks": []}],
                fixed=[{"id": "f1", "title": "会议", "start": "2026-10-02T13:00",
                        "end": "2026-10-02T14:00"}],
            ),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T12:00", "end": "2026-10-02T16:00"}
            ]},
            "expected_codes": ["C2"],
        },
    ],
})


# ---------- C3 ----------
write("c3_workhours_restdays.json", {
    "positive": [
        {
            "name": "块完整落在工作时段内且不在休息日",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T13:00"}
            ]},
        }
    ],
    "negative": [
        {
            "name": "块起点早于工作时段",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T08:00", "end": "2026-10-02T12:00"}
            ]},
            "expected_codes": ["C3"],
        },
        {
            "name": "块终点晚于工作时段",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T15:00", "end": "2026-10-02T19:00"}
            ]},
            "expected_codes": ["C3"],
        },
        {
            "name": "块跨越工作日（跨夜）",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T17:00", "end": "2026-10-02T20:00"}
            ]},
            "expected_codes": ["C3"],
        },
        {
            "name": "块落在周六（Python weekday=5）",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-03T10:00", "end": "2026-10-03T14:00"}
            ]},
            "expected_codes": ["C3"],
        },
        {
            "name": "块跨越休息日（周五晚到周六）",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T15:00", "end": "2026-10-02T20:00"}
            ]},
            "expected_codes": ["C3"],
        },
    ],
})


# ---------- C4 ----------
write("c4_dependencies.json", {
    "positive": [
        {
            "name": "后继块在前驱完成后开始",
            "project": project_with([
                {"id": "t1", "title": "前驱", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "后继", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
                {"taskId": "t2", "start": "2026-10-02T11:00", "end": "2026-10-02T13:00"},
            ]},
        },
    ],
    "negative": [
        {
            "name": "后继块早于前驱完成",
            "project": project_with([
                {"id": "t1", "title": "前驱", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "后继", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t2", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
                {"taskId": "t1", "start": "2026-10-02T11:00", "end": "2026-10-02T13:00"},
            ]},
            "expected_codes": ["C4"],
        },
        {
            "name": "前驱缺失且未排程",
            "project": project_with([
                {"id": "t2", "title": "后继", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t2", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
            ]},
            "expected_codes": ["C4"],
        },
        {
            "name": "依赖任务不存在",
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": ["ghost"], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
            ]},
            "expected_codes": ["C4"],
        },
    ],
})


# ---------- C5 ----------
write("c5_total_hours.json", {
    "positive": [
        {
            "name": "单任务块总时长等于剩余工时",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 6, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T15:00"},
            ]},
        },
        {
            "name": "单任务多块总时长等于剩余工时",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 6, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T12:00"},
                {"taskId": "t1", "start": "2026-10-05T09:00", "end": "2026-10-05T12:00"},
            ]},
        },
    ],
    "negative": [
        {
            "name": "块总时长少于剩余工时",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 6, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T12:00"},
            ]},
            "expected_codes": ["C5"],
        },
        {
            "name": "块总时长多于剩余工时",
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 4, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T15:00"},
            ]},
            "expected_codes": ["C5"],
        },
    ],
})


# ---------- C6 ----------
write("c6_overlap.json", {
    "positive": [
        {
            "name": "两块不重叠（首尾相邻）",
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
                {"taskId": "t2", "start": "2026-10-02T11:00", "end": "2026-10-02T13:00"},
            ]},
        }
    ],
    "negative": [
        {
            "name": "两块部分重叠",
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T11:00"},
                {"taskId": "t2", "start": "2026-10-02T10:00", "end": "2026-10-02T12:00"},
            ]},
            "expected_codes": ["C6"],
        },
        {
            "name": "一块完全包含另一块",
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 5,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T14:00"},
                {"taskId": "t2", "start": "2026-10-02T10:00", "end": "2026-10-02T12:00"},
            ]},
            "expected_codes": ["C6"],
        },
    ],
})


# ---------- C7 ----------
write("c7_adjustable.json", {
    "positive": [
        {
            "name": "被移动任务已标记 adjustable",
            "plan_changes": [
                {"blockId": "t1:b1",
                 "before": {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T09:00", "end": "2026-10-02T11:00",
                            "done": False},
                 "after":  {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T13:00", "end": "2026-10-02T15:00",
                            "done": False}},
            ],
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 2, "done": False, "dependsOn": [],
                "adjustable": True, "blocks": []}]),
        }
    ],
    "negative": [
        {
            "name": "被移动任务未标记 adjustable",
            "plan_changes": [
                {"blockId": "t1:b1",
                 "before": {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T09:00", "end": "2026-10-02T11:00",
                            "done": False},
                 "after":  {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T13:00", "end": "2026-10-02T15:00",
                            "done": False}},
            ],
            "project": project_with([{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 2, "done": False, "dependsOn": [],
                "adjustable": False, "blocks": []}]),
            "expected_codes": ["C7"],
        },
        {
            "name": "多个被移动任务中之一未授权",
            "plan_changes": [
                {"blockId": "t1:b1",
                 "before": {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T09:00", "end": "2026-10-02T11:00",
                            "done": False},
                 "after":  {"id": "b1", "taskId": "t1",
                            "start": "2026-10-02T13:00", "end": "2026-10-02T15:00",
                            "done": False}},
                {"blockId": "t2:b2",
                 "before": {"id": "b2", "taskId": "t2",
                            "start": "2026-10-05T09:00", "end": "2026-10-05T11:00",
                            "done": False},
                 "after":  {"id": "b2", "taskId": "t2",
                            "start": "2026-10-05T13:00", "end": "2026-10-05T15:00",
                            "done": False}},
            ],
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1, "remainingHours": 2,
                 "done": False, "dependsOn": [], "adjustable": False, "blocks": []},
            ]),
            "expected_codes": ["C7"],
        },
    ],
})


# ---------- 组合场景 ----------
write("combined.json", {
    "scenarios": [
        {
            "name": "三任务正常排程（全约束满足）",
            "project": project_with([
                {"id": "t1", "title": "领域模型与校验器", "priority": 1,
                 "remainingHours": 6, "done": False, "dependsOn": [],
                 "adjustable": True, "blocks": []},
                {"id": "t2", "title": "Agent 循环与工具", "priority": 1,
                 "remainingHours": 6, "done": False, "dependsOn": ["t1"],
                 "adjustable": True, "blocks": []},
                {"id": "t3", "title": "客户端执行器与回读", "priority": 2,
                 "remainingHours": 4, "done": False, "dependsOn": ["t2"],
                 "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T15:00"},
                {"taskId": "t2", "start": "2026-10-06T09:00", "end": "2026-10-06T15:00"},
                {"taskId": "t3", "start": "2026-10-07T09:00", "end": "2026-10-07T13:00"},
            ]},
            "expected_codes": [],
        },
        {
            "name": "三任务 C5 + C4 + C6 同时违规",
            "project": project_with([
                {"id": "t1", "title": "t", "priority": 1, "remainingHours": 4,
                 "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1, "remainingHours": 4,
                 "done": False, "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            ]),
            "candidate": {"blocks": [
                {"taskId": "t1", "start": "2026-10-02T09:00", "end": "2026-10-02T12:00"},
                {"taskId": "t2", "start": "2026-10-02T10:00", "end": "2026-10-02T14:00"},
            ]},
            "expected_codes": ["C4", "C5", "C6"],
        },
    ]
})

print("written:")
for p in sorted(OUT.iterdir()):
    print(" ", p)
