---
phase: quick-260909-ke1
plan: 01
subsystem: diagnostics + gui/canvas
tags: [logging, crash-capture, hang-watchdog, faulthandler, loguru, inline-editor, breadcrumbs]
status: complete
requires:
  - manga_ai_studio/__main__.py main() entrypoint
  - loguru (0.7.3, already a dependency; zero sinks were configured before this task)
  - PySide6 6.10.1 (slot->sys.excepthook routing, proven empirically)
provides:
  - manga_ai_studio/diagnostics.install() — one-call file sink + excepthooks + hang watchdog (idempotent, Qt-free at module scope)
  - diagnostics.install_qt_message_handler() — Qt warnings/criticals routed into mas.log
  - diagnostics.heartbeat(app) / stop_heartbeat() — event-loop-kept faulthandler watchdog (mas-hang.log)
  - InlineEditor.active_box_item — the single staleness surface for delete-path guards
  - gui-namespace DEBUG breadcrumbs along copy/delete/paste/editor paths
affects:
  - every future crash/freeze report now carries on-disk evidence
  - tests/test_diagnostics.py, tests/test_gui_diagnostics.py, tests/test_gui_paste_freeze_repro.py
tech-stack:
  added: []
  patterns:
    - faulthandler.dump_traceback_later watchdog + heartbeat cancel/re-arm (works without the frozen main thread's cooperation)
    - mas-hang.log deliberately SEPARATE from the loguru sink file (fd-level writes vs appender interleaving on Windows)
    - loguru enqueue=True sink + logger.complete() drain in tests (fifo-ordered barrier-anchored absence checks)
    - pytest-qt qt_no_exception_capture marker where the test asserts the excepthook path itself
key-files:
  created:
    - manga_ai_studio/diagnostics.py
    - tests/test_diagnostics.py
    - tests/test_gui_diagnostics.py
    - tests/test_gui_paste_freeze_repro.py
  modified:
    - manga_ai_studio/__main__.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/inline_editor.py
    - manga_ai_studio/gui/main_window.py
decisions:
  - "Qt message handler installed AFTER create_app (per the plan's <behavior>+Design; the <action>'s inline ordering said before — behavior/Design treated as authoritative)"
  - "install(hang_timeout_s=...) parameter carries the watchdog deadline override (module constant HANG_TIMEOUT_S=60.0 never mutated; tests pass 0.1/0.5)"
  - "Hang dumps go to a dedicated mas-hang.log fd, never the loguru file — faulthandler writes raw from its watchdog thread"
  - "Slot-exception proof test uses pytest-qt's official qt_no_exception_capture escape hatch — their capturer replaces sys.excepthook per test and would re-fail the test for the very exception being asserted as logged"
  - "Partial-delete guard commits the editor ONLY when its own box is among the retiring items (an open edit on box B survives deleting box A)"
metrics:
  duration: 23 min
  completed: 2026-09-09
  tasks: 3
  files: 8
actuals:
  tokens: 14000
  tasks: 3
  commits: 5
---

# Quick Task 260909-ke1: Stability — file logging + crash/freeze diagnostics; paste-after-delete freeze investigation — Summary

Rotating file logging + crash/hang capture (loguru sink, excepthooks, faulthandler watchdog, Qt message routing) plus a headless repro harness for the reported freeze that found and fixed the one demonstrable defect: the delete paths left the inline editor dangling over a retired box.

## What Was Built

**Deliverable 1 — diagnostics infrastructure (Tasks 1–2).** The app previously had zero diagnostics: loguru had no sinks (every `logger.*` died with the console), and no `sys.excepthook` / `threading.excepthook` / `faulthandler` / `qInstallMessageHandler` existed anywhere. Now:

- `manga_ai_studio/diagnostics.py` (NEW, Qt-free at module scope — AST-scan + subprocess-import locked): `install()` adds ONE rotating sink (`~/.manga_ai_studio/logs/mas.log`, 5 MB / retention 3 / utf-8 / `enqueue=True` so a slow disk never stalls the GUI thread) with the modest-volume filter (WARNING+ everywhere, DEBUG admitted only for `manga_ai_studio.gui.*` names, `session_marker` extra admits the separator), wraps `sys.excepthook` + `threading.excepthook` (traceback at ERROR, previous hook chained, never swallowed), enables `faulthandler` + `dump_traceback_later(60s, repeat)` into a dedicated `logs/mas-hang.log`, and writes the v0.1.0/timestamp/platform session separator. Idempotent; `reset()` for tests.
- `heartbeat(app)` arms a QApplication-parented QTimer (15 s default) whose tick cancels + re-arms the watchdog deadline: a live loop never dumps, a wedged main thread stops ticking and an all-thread stack dump lands in mas-hang.log ~60 s in — zero code changes needed at freeze time.
- `install_qt_message_handler()` maps QtDebug/Info/Warning/Critical/Fatal to loguru levels with file:line context; previous handler restored on reset.
- `__main__.main()` wiring: `diagnostics.install()` FIRST → `create_app` → Qt handler → heartbeat → `[manga-ai-studio] log file: ...` printed to stderr → existing profile/MainWindow/exec sequence unchanged.

**Deliverable 2 — freeze investigation (Task 3).** `tests/test_gui_paste_freeze_repro.py` scripts the reported sequence twice:

- **Sequence A (the report, verbatim — canary, passed before AND after the fix):** Ctrl+click copy-text (spy observed) → Ctrl+C box copy → Delete box A (graveyard-retired) → resize-expand box B → Ctrl+V paste. No exception, consistent layer state, text round-trips onto the pasted clone.
- **Sequence B (stale-editor variant — RED then GREEN):** with the inline editor open on box A and an uncommitted edit, the Delete branch left the editor ACTIVE over the retired BoxItem (see RED evidence below); a later commit would write text into a removed PageBox and emit a bogus `boxes_modified` AFTER the removal emission — undo corruption, inside a Qt slot in the real app. Fixed with the commit-first guard mirroring the `set_boxes` precedent (`canvas.py:2675`).
- **Breadcrumbs:** nine one-line `logger.debug` calls (gui-namespace loggers, admitted by the Task 1 filter at DEBUG): copy-text emit, `copy_boxes`, `delete_key` (with editor-active state), paste entry/exit, graveyard release, `inline_editor_commit`/`inline_editor_cancel`, MainWindow `clipboard_write`. No per-paint or per-mouse-move logging anywhere (the task's harness asserts the exact lines against a real `install()` sink).

## RED → GREEN Evidence

**Task 1 RED:** collection ImportError — `cannot import name 'diagnostics' from 'manga_ai_studio'` (module did not exist). Committed `1ee7f85`, then implemented in `2e4f99e` (13/13 headless).

**Task 2 RED:** 4/5 failed (`install_qt_message_handler`/`heartbeat` missing, `__main__` unwired). The slot-exception test passed pre-implementation because Task 1's hook is its mechanism — the empirical proof value is unchanged. Committed `890a3fa`, implemented in `a2cbe53` (18/18).

**Task 3 RED (committed as the single atomic GREEN commit `e35b4b8`, task type is `auto`):**

```
assert not canvas._inline_editor.is_active()
E   assert not True
E    +  where True = is_active()
```

After the delete, the editor was still open on the retired item, and only ONE `boxes_modified` had fired (the removal) — the commit-first emission was missing. After the guard: editor closed by the delete path, exactly two ordered emissions (commit BEFORE-snapshot carries the ORIGINAL text, removal BEFORE-snapshot carries the committed text), `edited=True` via the D-04 setter, and post-graveyard `commit()` is a safe no-op.

**Empirical proof recorded (plan demanded proving it on the installed version):** PySide6 6.10.1 DOES route slot exceptions raised via `QTimer.singleShot(0, ...)` to `sys.excepthook` — probe showed the traceback in mas.log and the event loop SURVIVING (`PUMP ALIVE AFTER SLOT ERROR`).

## Deviations from Plan

**1. [Plan-internal inconsistency] Qt handler ordering in `__main__`:** the `<action>` ordered `install_qt_message_handler()` before `create_app`; the `<behavior>` + Design + frontmatter artifacts all say "installs the Qt message handler + heartbeat after create_app". Followed behavior/Design (install FIRST, handler after create_app). The tested contract is the behavior bullet.

**2. [Platform truth] faulthandler dump header:** the plan's behavior text expected `"Current thread"` in mas-hang.log; measured output on this Windows/CPython 3.14.2 box is `Timeout (0:00:00.100000)!` + `Thread 0x... (most recent call first):` (the "Current thread" label only appears when the crashing thread dumps itself). The test asserts the measured truth ("Timeout" + "(most recent call first)") — the ≤60 s wedge evidence contract is unchanged.

**3. [Test infrastructure] slot-exception test marker:** pytest-qt replaces `sys.excepthook` per test and re-fails the test at the end for captured exceptions — including the very exception this test asserts was LOGGED. The test carries `@pytest.mark.qt_no_exception_capture` (pytest-qt's official escape hatch, `plugin.py`), leaving the diagnostics hook as the system excepthook under test.

**4. [Diagnosis precision] the `RuntimeError` variant of the stale-editor defect:** the harness demonstrates the dangling editor and the bogus post-removal emission deterministically; the literal `RuntimeError: Internal C++ object already deleted` is ref-timing dependent (the editor's own strong ref keeps the C++ item alive in the headless harness). The guard removes the entire family regardless — commit now always happens while the box is still live.

## Flagged Candidates (found, NOT fixed — scope discipline)

- **Paste page-clamp overflow** — `manga_ai_studio/gui/canvas.py` `_paste_boxes` (was ~3397–3401, now ~3434–3438 after breadcrumbs): when the clipboard box is wider/taller than the page, `max(0, page_w - w)` collapses the origin to 0 but KEEPS `w`/`h`, producing an out-of-page rect that contradicts the "Clamp the pasted rect inside the page" comment. Not reachable from the reported repro (pasted box is source-box-sized); candidate for a future quick task.

## Verification

1. All three new batteries: `tests/test_diagnostics.py` (13) + `tests/test_gui_diagnostics.py` (5) + `tests/test_gui_paste_freeze_repro.py` (4) = **22 passed**.
2. Full suite: **1432 passed, 0 failed** (181.95 s) — strict superset of the 1410 baseline (1410 + 22 new); no flakes to triage.
3. Boot spot-check: `python -m manga_ai_studio` prints `[manga-ai-studio] log file: ...` to stderr (wiring order test-locked); `%USERPROFILE%\.manga_ai_studio\logs\mas.log` receives the session separator naming v0.1.0; mas-hang.log stays empty while the loop ticks and gains an all-thread dump after a >60 s main-thread wedge (deterministic short-timeout mechanics test-locked both ways).
4. Log volume: breadcrumbs are one line per user action only — structurally no per-paint/per-mouse noise (asserted by line-level checks in the harness).

**Human spot-check still worthwhile (visual/manual):** launch via `start.bat`, edit a few minutes, confirm mas.log shows only separator + action breadcrumbs, and `%USERPROFILE%\.manga_ai_studio\logs\` contains both files.

## Known Stubs

None. Every new code path is wired end-to-end (entrypoint → module → file), and the harness proves the sink/handler/guard behavior on the installed versions.

## Commits

| Task | Commit | Content |
|------|--------|---------|
| 1 RED | 1ee7f85 | test: diagnostics core battery |
| 1 GREEN | 2e4f99e | feat: diagnostics core — sink, excepthooks, watchdog |
| 2 RED | 890a3fa | test: Qt diagnostics integration battery |
| 2 GREEN | a2cbe53 | feat: Qt message routing, heartbeat, entrypoint wiring |
| 3 | e35b4b8 | fix: repro harness + inline-editor staleness guard + breadcrumbs |

TDD gate compliance: `test(...)` commits precede `feat(...)` commits for Tasks 1 and 2; Task 3 is `type="auto"` with RED evidence captured above in a single atomic commit.

## Self-Check: PASSED

- All 8 plan files exist on disk (verified 2026-09-09) + the SUMMARY itself.
- All 5 commit hashes present in history (1ee7f85, 2e4f99e, 890a3fa, a2cbe53, e35b4b8).
- `git status` shows zero uncommitted changes under `manga_ai_studio/` and `tests/` (pre-existing `.planning/` archive deletions untouched — not part of this task).
- Full suite re-verified at close: 1432 passed / 0 failed (strict superset of the 1410 baseline).
