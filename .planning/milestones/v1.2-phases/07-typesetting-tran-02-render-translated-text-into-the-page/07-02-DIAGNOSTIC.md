# 07-02 Diagnostic: Native Crash in Full-Run GUI Test Battery

**Status:** INVESTIGATING → RESOLVED (see timeline)
**Filed:** continuation executor, plan 07-02 (multi-select wave)
**Crash signature:** `Windows fatal exception: access violation` — process exit
`-1073741819` (0xC0000005).

---

## 1. Symptom

Running the full `tests/test_gui_boxes.py` battery (168 tests) on the 07-02
working tree dies with a NATIVE access violation (no Python exception) inside:

```
File "manga_ai_studio/gui/box_item.py", line 333 in paint
    painter.drawPixmap(QPointF(0.0, 0.0), self._pixmap)
```

The crash fires from `pytestqt.plugin._process_events` — i.e. while Qt flushes
deferred paint events — right after `test_text_overlay_content_refresh_keeps_scene_px_style`
passes and while `test_zoom_changed_reapplies_overlay_style_canvas` runs.

### Key facts established by reproduction (2026-08-11, pinned interpreter 3.14.2)

| Probe | Result |
|-------|--------|
| Working tree, full file run | CRASH (access violation, reproducible 3/3) |
| Working tree, the 2 overlay tests alone | pass (2/2) |
| **Baseline HEAD (b61adcb), full file run** | **NO crash** — 168 passed, 1 env failure (`test_run_ocr_selected_real_model_end_to_end`, model-less CI env) |
| `QAction("Select All Boxes", w)` + `setShortcut("Ctrl+A")` + menu insert, standalone | constructs + exits cleanly, EXIT 0 |

**Conclusion so far:** the crash is INTRODUCED by the 07-02 in-progress
changes (staged `canvas.py`/`box_item.py` + unstaged `main_window.py`). It is a
heap-layout-dependent use-after-free of the `TextOverlayItem._pixmap` C++
object, not a Python-level logic error.

## 2. The "QAction problem" theory (prior session) — RED HERRING

The cancelled prior session left this probe in `main_window.py` `__init__`:

```python
# BISECT: bare extra QAction (no parent) in __init__ (allocation probe)
self._bisect_action = QAction("Bisect")
```

The comment shows the prior session believed the crash was caused by the
Ctrl+A "Select All Boxes" QAction allocation ("allocation probe"). That
hypothesis is **disproven**:

- `QAction("Select All Boxes", w)` with `setShortcut(QKeySequence("Ctrl+A"))`
  and a menu insert constructs and tears down cleanly in isolation (EXIT 0).
- A parentless bare `QAction("Bisect")` in `__init__` is the *current state of
  the file* and the crash STILL reproduces with it present — so it neither
  causes nor prevents the crash.
- The probe DID have a plausible role in the prior session: allocating the
  extra QAction shifts the C++ heap, which can move a use-after-free's
  manifestation point. The crash's appearance/disappearance across runs is
  heap-layout sensitivity, not causation.

The crash is a genuine use-after-free in the text-overlay paint path; the
QAction probe is unrelated debris to be REMOVED once the UAF is fixed.

## 3. Root cause (established during this continuation session)

The 07-02 staged `canvas.py` change to `set_boxes()` — the layer-rebuild path
called on every page load, undo/redo restore, and `_canvas_with_image_and_boxes`
test setup — resets the multi-select state **but the rebuild loop keeps the
`BoxItem.set_primary_owner(_weakref(self))` wiring**, and the UAF manifests
through the primary-owner consultation in `BoxItem._sync_handles_for_state`:

```python
if selected and self._primary_owner is not None:
    canvas = self._primary_owner()          # weakref deref
    if canvas is not None:
        primary = canvas._is_primary_provider(self)
        if primary is not None:
            show = bool(primary)
```

[Full analysis + fix record follows — see section 4.]

## 4. Analysis and fix

(filled in below as the investigation completes — the file is appended to
rather than rewritten so the record survives any failed fix attempt)

---

## Investigation log

### 2026-08-11 — continuation executor

- Reproduced crash 3/3 on working tree; 0/3 on baseline HEAD.
- Disproven QAction-causation theory (section 2).
- Root-cause analysis and fix: see `## Root Cause` + `## Fix` sections appended
  below.

---

## Root Cause

The use-after-free is a **PySide6 QGraphicsItem child-ownership teardown race**
triggered by the 07-02 additions, in combination with pytest-qt's deferred
paint flushing:

1. `test_text_overlay_content_refresh_keeps_scene_px_style` builds a **bare
   scene** via `_scene_with_box()` — a `QGraphicsScene` whose `BoxItem` has
   **no canvas/primary-owner installed** (`_primary_owner is None`).
2. The test ends. Python GC collects the scene and item wrappers. PySide6
   deletes the C++ `QGraphicsScene`; the C++ `BoxItem` and its child
   `TextOverlayItem` are destroyed **while a paint event for the overlay is
   still queued** in the Qt event queue.
3. The NEXT test's `qtbot` fixture calls `_process_events`, which flushes that
   stale paint event. Qt dispatches it to the `TextOverlayItem` C++ object —
   whose backing storage was freed. `paint()` enters via the stale wrapper and
   `painter.drawPixmap(..., self._pixmap)` reads freed memory → access
   violation.
4. **Why 07-02 makes this fire where Phase 3/07-01 didn't:** the 07-02
   `BoxItem.__init__` addition `self._primary_owner = None` and the
   `_sync_handles(primary=...)` rework changed the object graph and
   `itemChange`→`_sync_handles_for_state` call frequency *and* the canvas
   change calls `_sync_handles_visibility()` (per-item `_sync_handles` sweep)
   in new paths (`_clear_selection`, `_toggle_box_selection`,
   `_refresh_primary_box`, `_select_and_begin_move`). Every extra
   `setVisible`/`update()` on the overlay schedules another deferred paint,
   widening the teardown race window until the stale-event flush lands on
   freed memory.

This is a latent pre-existing teardown hazard (any bare-scene test that
renders the overlay can race), made REACHABLE and crash-y by 07-02's new
paint-scheduling paths.

---

## VERIFIED ROOT CAUSE + FIX (controlled experiments, 2026-08-11)

### Controlled experiments (full `tests/test_gui_boxes.py` battery, pinned 3.14.2)

| # | State | Result |
|---|-------|--------|
| A | 07-02 canvas.py + box_item.py (staged) + main_window.py reverted to HEAD | **169 passed, no crash** |
| B | all 07-02 changes, probe REMOVED | **169 passed, no crash** (2/2 runs) |
| C | all 07-02 changes, probe present parentless (`QAction("Bisect")`) | **CRASH** (3/3 runs, exit -1073741819) |
| D | all 07-02 changes, probe present PARENTED (`QAction("Bisect", self)`) | **CRASH** |

### Verdict

- The crash trigger is the **extra QAction allocation in `__init__`** — *any*
  extra QAction (parented or not) perturbs the C++ heap layout enough to expose
  a **latent, heap-layout-dependent teardown use-after-free**: `TextOverlayItem.paint`
  (`box_item.py:333`, `painter.drawPixmap(..., self._pixmap)`) reads a QPixmap
  whose C++ object was freed when a bare-scene test's `QGraphicsScene` was
  garbage-collected with a paint event still queued (pytest-qt flushes it at
  the next test's `_process_events`).
- The UAF origin is not fully pinned: baseline HEAD passes, and the 07-02
  changes alone (without the probe) pass — only the probe's heap perturbation
  exposes the fault. Whether the race window predates 07-02 or is widened by
  its new paint-scheduling paths is not conclusively established; either way it
  is OUT OF SCOPE for 07-02 because it does not manifest with the plan's actual
  code, and it is logged to `deferred-items.md` for a future robustness plan.
- **The 07-02 fix: delete the BISECT probe** (diagnostic debris left by the
  cancelled session — never part of the plan). All 07-02 logic (group move,
  group delete, op-name plumbing, primary-handle gate) is verified green
  without it.
- **Task 1's real action verified safe:** the plan's `action_select_all_boxes`
  QAction was created in `_build_edit_menu` with the other Edit actions
  (parented, `setShortcut("Ctrl+A")`, zero-arg-lambda `triggered` connect) —
  NOT in `__init__` (the crash-prone allocation site). The full battery and
  the entire test suite ran green with it in place (646 passed, 0 failed).
- **Resolution:** the crash is gone, the probe is deleted, all 07-02 tasks are
  committed (3 commits), and the full suite passes. The latent teardown race
  is tracked in `deferred-items.md` for a future robustness plan.

## Fix

**Chosen fix (final): delete the BISECT probe** (`self._bisect_action =
QAction("Bisect")`) from `main_window.py` `__init__` — proven debris by the
controlled experiments above (present → crash 3/3; absent → green 2/2). The
real `action_select_all_boxes` action lives in `_build_edit_menu` (parented,
shortcut-wired) and is verified crash-free across the full suite.
