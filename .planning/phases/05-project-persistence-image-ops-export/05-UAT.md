---
status: testing
phase: 05-project-persistence-image-ops-export
source: [05-VERIFICATION.md]
started: 2026-08-08T18:30:00Z
updated: 2026-08-08T19:10:00Z
---

## Current Test

number: 2
name: MVP goal-format decision
expected: |
  Decide whether the Phase 5 goal's non-user-story phrasing is acceptable (precedent: phases 01-04 verified passed against Success Criteria) or whether the goal should be re-formatted via /gsd-mvp-phase 5.
awaiting: user response

## Tests

### 1. CR-01 end-to-end repro — post-op image persists across navigation and save
expected: Rotate page 2 → navigate to another page → navigate back → save → reopen. The rotation must persist: display shows the rotated image, the saved .mas embeds the post-op image, and boxes/text are still aligned.
result: issue
reported: "Open Project… does nothing; console traceback: AttributeError: 'bool' object has no attribute 'name' at main_window.py:2065 (QAction.triggered bool passed as manifest_path). Save Project As… default path is a non-existent .mas-project folder — dialog falls back to album root and the whole project saves as .mas files in the album root. Loading via Recent Projects works as expected."
severity: blocker

### 2. MVP goal-format decision
expected: Decide whether the Phase 5 goal's non-user-story phrasing is acceptable (precedent: phases 01-04 verified passed against Success Criteria) or whether the goal should be re-formatted via /gsd-mvp-phase 5.
result: [pending]

## Summary

total: 2
passed: 0
issues: 1
pending: 1
skipped: 0
blocked: 0

## Gaps

- gap_id: G-05-1
  truth: "Open Project… opens the selected manifest.json or .mas and resumes the session"
  status: failed
  reason: "User reported: Open Project does nothing; AttributeError: 'bool' object has no attribute 'name' (main_window.py:2065) — the QAction.triggered checked-bool is passed as manifest_path so selected=False"
  severity: blocker
  test: 1
  artifacts: []
  missing: []

- gap_id: G-05-2
  truth: "Save Project As… defaults to a <chapter>.mas-project folder beside the source and writes the project inside it (D-02)"
  status: failed
  reason: "User reported: the .mas-project default path does not exist so the dialog falls back to the album root; saving then wrote manifest.json + .mas files into the album root"
  severity: major
  test: 1
  artifacts: []
  missing: []
