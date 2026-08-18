---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 0
total_count: 2
last_updated: 2026-08-17T23:57:46.124Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 07 | deviation | tests/test_core/test_typeset_layout.py |  | 07-07 Task 3 test-contract adjustment: plan's square-ish (w >= h - tolerance) assertion for upright Latin impossible on real font metrics (line-box 15.62px > advance 9.33px at 14px); replaced with column-extent assertions (upright width-based x==0, rotated height-based x>w) | open |  | 2026-08-12T03:16:41.398Z |  |
| 2 | 08 | deviation | manga_ai_studio/gui/main_window.py |  | Box delete does not recompose/refit the auto plane - deleted detected box's auto content lingers until the next refresh trigger (move/resize/create only per 08-07 trigger set) | open |  | 2026-08-17T23:57:46.124Z |  |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "07",
    "file": "tests/test_core/test_typeset_layout.py",
    "line": null,
    "description": "07-07 Task 3 test-contract adjustment: plan's square-ish (w >= h - tolerance) assertion for upright Latin impossible on real font metrics (line-box 15.62px > advance 9.33px at 14px); replaced with column-extent assertions (upright width-based x==0, rotated height-based x>w)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-12T03:16:41.398Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "deviation",
    "phase": "08",
    "file": "manga_ai_studio/gui/main_window.py",
    "line": null,
    "description": "Box delete does not recompose/refit the auto plane - deleted detected box's auto content lingers until the next refresh trigger (move/resize/create only per 08-07 trigger set)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-17T23:57:46.124Z",
    "resolved_at": null
  }
]
````
