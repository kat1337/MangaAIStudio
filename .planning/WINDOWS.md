---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-08-12T03:16:41.398Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 07 | deviation | tests/test_core/test_typeset_layout.py |  | 07-07 Task 3 test-contract adjustment: plan's square-ish (w >= h - tolerance) assertion for upright Latin impossible on real font metrics (line-box 15.62px > advance 9.33px at 14px); replaced with column-extent assertions (upright width-based x==0, rotated height-based x>w) | open |  | 2026-08-12T03:16:41.398Z |  |

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
  }
]
````
