---
status: diagnosed
trigger: "BLOCKER: app crashes when pressing Ctrl+Z (undo) after styling interactions (Phase 7 typesetting). Diagnose only, no fix."
created: 2026-08-11T18:30:00Z
updated: 2026-08-11T21:10:00Z
---

## Current Focus
hypothesis: CONFIRMED — the Ctrl+Z crash is the deferred-items.md latent overlay teardown UAF manifesting in the real app via the undo-rebuild path (canvas.set_boxes synchronous C++ item deletion with pending scene updates). Native crash: pure-virtual paint dispatch on a freed QGraphicsItem (VCRUNTIME _purecall -> abort 0xc0000409/7), proven by the user's crash dump (python.exe.56276.dmp, 2026-08-11 20:20:43, UAT window).
test: (complete — dump analysis + code-path analysis + differential probe)
expecting: n/a — diagnosis complete (diagnose-only mode)
next_action: Return structured ROOT CAUSE FOUND report. No fix (diagnose-only).

## Symptoms
expected: Ctrl+Z undoes last styling operation without crashing
actual: App crashes natively when pressing Ctrl+Z after Inspector styling session (UAT test 3, G-07-6). Crash dump: python.exe.56276.dmp, Event Log: python.exe, 0xc0000409, ucrtbase.dll+0xa527e, 2026-08-11 20:20:16 (dump 20:20:43) — mid-UAT window.
errors: 0xc0000409 FAST_FAIL_FATAL_APP_EXIT param[0]=7 (abort); faulting thread stack top = VCRUNTIME140.dll+0x59EA (pure-virtual-call handler), below it Qt6Widgets/Qt6Gui paint machinery + python314 callback + ucrtbase (memcpy) frames — the TypesetOverlayItem.paint -> drawPixmap path.
reproduction: load page, run OCR, Ctrl+A select ALL boxes, style via Inspector (real QFontComboBox font + QColorDialog color), press Ctrl+Z
started: after Phase 7 (per-box TextStyle, TypesetOverlayItem, grouped ops)

## Eliminated
- hypothesis: "History manager / PageBox.copy() / TextStyle undo data corruption"
  evidence: history_manager.py fully read — every push/pop materializes fresh detached snapshots; PageBox.copy() detaches payload+style; TextStyle pure-Python. No stale references, no deleted-object access at the Python level.
  timestamp: 2026-08-11T19:00:00Z
- hypothesis: "Python-level exception (shiboken RuntimeError on deleted C++ object) in the undo chain"
  evidence: Every Python-level path in the undo chain (on_undo 3382, _current_undo_state 3362, _apply_undo_result 3417, apply_undo_boxes 3455, _on_boxes_modified 2876 suppressed, _set_session_dirty 1974 suppressed) is guard-clean; a Python exception in a Qt slot prints a traceback and the app continues — the crash dump shows a HARD native abort (0xc0000409) with a C++ pure-virtual-call frame, not a Python exception path.
  timestamp: 2026-08-11T20:40:00Z
- hypothesis: "Renderer (text_renderer.py layout/paint) crashes during undo restore re-render"
  evidence: The restore re-renders the same styles/fonts the commit path already rendered successfully (user styled boxes before the crash); renderer is pure Qt+QImage with all the documented crash-avoidance discipline (plain documents, forced layout, bounded effect surfaces).
  timestamp: 2026-08-11T20:00:00Z

## Evidence
- timestamp: 2026-08-11T18:45:00Z
  checked: history_manager.py full read
  found: _materialize_snapshot + push/pop .copy() detachment everywhere. No stale refs.
  implication: History layer is not the crash site.

- timestamp: 2026-08-11T18:50:00Z
  checked: main_window.py undo chain
  found: The ONLY native-object-mutating step in the whole undo path is canvas.set_boxes — the layer rebuild that removes + destroys the old BoxItems (apply_undo_boxes -> set_boxes).
  implication: set_boxes is the crash site candidate.

- timestamp: 2026-08-11T18:55:00Z
  checked: canvas.set_boxes 1622-1675
  found: removeItem per old box; then _box_items=[] (1652), _selection_order=[] (1654), _primary_box=None (1655), _group_move={} (1656) drop the LAST strong Python refs -> CPython refcount 0 -> shiboken synchronously deletes the C++ BoxItem + children (CornerHandles, TypesetOverlayItem, badge) INSIDE set_boxes, mid-event-loop. New BoxItem allocations (1658+) immediately reuse the freed blocks (heap-layout dependence).
  implication: Bulk C++ deletion of overlay-carrying items with pending scene updates = the 07-02 UAF family.

- timestamp: 2026-08-11T18:58:00Z
  checked: box_item.py TypesetOverlayItem 295-408
  found: paint() at 331-334 -> painter.drawPixmap(0,0,self._pixmap) — THE documented 07-02 crash line (deferred-items.md: box_item.py:333, exit -1073741819). set_content ends with self.update() (396) — every style commit / text refresh queues a scene update for the overlay. refresh_text_overlay is called per selected box on EVERY style commit (main_window 3022-3024).
  implication: Pending scene updates referencing the soon-to-be-deleted overlays exist at Ctrl+Z time.

- timestamp: 2026-08-11T19:00:00Z
  checked: tests/test_gui_inspector_styling.py test_style_commit_applies_to_all (399-434)
  found: The ONLY style-commit+on_undo test holds the old BoxItem wrappers alive in its `items` local across on_undo() — C++ deletion deferred to test teardown. Test helpers (test_gui_boxes.py:2788-2800) all return the item lists.
  implication: Differential — the test CANNOT reproduce the app crash because the item lifetime differs (deferred vs synchronous deletion). This is why the bug passed the suite.

- timestamp: 2026-08-11T19:30:00Z
  checked: 07-02-DIAGNOSTIC.md + deferred-items.md
  found: Same crash signature (overlay paint drawPixmap, native); documented heap-layout-dependent ("extra QAction allocation deterministically exposes it"); latent UAF open + deferred to a robustness plan.
  implication: The in-app Ctrl+Z crash is a NEW manifestation path (item-deletion variant) of the SAME latent UAF — not a new defect class.

- timestamp: 2026-08-11T20:20:00Z
  checked: %LOCALAPPDATA%\CrashDumps\python.exe.56276.dmp + Windows Event Log (id 1000)
  found: Exception 0xc0000409, param[0]=0x7 (FAST_FAIL_FATAL_APP_EXIT = abort), faulting address ucrtbase.dll+0xa527e, thread 49536. Stack scan of the faulting thread: top frame VCRUNTIME140.dll+0x59EA (the C++ pure-virtual-call abort handler _purecall); below: Qt6Widgets.dll (+0x3C1FEA/+0x3C47E7/+0x3C6798/+0x3C52B0/+0x3AFE2A/+0x3CDB62), Qt6Gui.dll (+0xAB7B8/+0xACC11/+0x1D7530/+0x137452 — QPainter drawPixmap/drawImage machinery), python314.dll+0x6E0D10 (Python callback — the TypesetOverlayItem.paint override), ucrtbase (memcpy-ish +0x50D9), QtWidgets.pyd/shiboken6 trampolines, qwindows.dll (real windows platform). Modules include torch_python/cudnn/openblas — the FULL app heap.
  implication: NATIVE crash (not Python exception) in the Qt graphics paint dispatch with the overlay's Python paint override on the stack — the UAF signature. QGraphicsItem::paint is pure virtual: a paint dispatched to a freed TypesetOverlayItem whose Python wrapper is dead calls the pure-virtual -> _purecall -> abort(0xc0000409/7). This is EXACTLY the observed dump.

- timestamp: 2026-08-11T20:50:00Z
  checked: Empirical probes (offscreen, app-like): (1) style-commit->undo with refs dropped, no event flush between (200 iters), (2) raw Qt item-deletion with pending update (2000 iters), (3) scene-teardown variant (2000 iters) — all survived.
  found: The UAF is heap-layout-dependent (07-02 lesson); the probes' quiet heap (no torch/cudnn/QColorDialog/font-database churn) never perturbs freed overlay memory into the crash configuration.
  implication: Non-reproduction in probes is CONSISTENT with the documented heap-layout dependence; the dump is the decisive evidence.

## Resolution
root_cause: |
  NATIVE crash (not a Python exception) — the deferred-items.md latent
  "text-overlay teardown UAF" (07-02) manifesting in the real app through the
  Ctrl+Z undo path:

  1. Inspector style commits (multi-select, per selected box) call
     refresh_text_overlay -> TypesetOverlayItem.set_content -> self.update()
     (box_item.py:396), queueing scene updates that reference the overlay
     items (QGraphicsScenePrivate::updates + posted UpdateRequest).
  2. Ctrl+Z -> MainWindow.on_undo (main_window.py:3382) -> apply_undo_boxes
     (3455) -> EditorCanvas.set_boxes (canvas.py:1622). set_boxes removes
     every BoxItem from the scene (1650-1651) and then drops the LAST strong
     Python references (_box_items/_selection_order/_primary_box/_group_move,
     1652-1656) -> CPython refcount 0 -> shiboken synchronously deletes the
     C++ BoxItems and their TypesetOverlayItem children MID-EVENT-LOOP, while
     the scene's pending-update list still holds pointers to those items
     (the last commit's updates were not yet flushed; the Ctrl+Z key event is
     processed before the posted UpdateRequest on the Windows message pump).
  3. The next event-loop flush (QGraphicsScenePrivate::processPendingUpdates
     or the viewport paint) dispatches paint() to a FREED TypesetOverlayItem.
     With the Python wrapper dead, the dispatch lands on the pure-virtual
     QGraphicsItem::paint -> VCRUNTIME _purecall -> abort() ->
     0xc0000409 FAST_FAIL_FATAL_APP_EXIT (dump param[0]=7). In the
     heap-reuse variant the freed block is reused -> garbage vtable -> wild
     call inside QPainter::drawPixmap (Qt6Gui frames in the dump).
  Crash evidence: python.exe.56276.dmp (20:20:43, UAT window) — faulting
  thread stack: VCRUNTIME140 (_purecall) -> Qt6Widgets/Qt6Gui paint
  machinery -> python314 callback (the paint override) -> ucrtbase memcpy —
  the exact 07-02 signature line (box_item.py:333-334 drawPixmap).
  Why tests don't catch it: every GUI test helper returns the BoxItem list
  (test_gui_boxes.py:2788-2800; test_gui_inspector_styling.py:315-324), so
  the old wrappers stay alive across set_boxes and C++ deletion is deferred
  to window teardown (the 07-02 scene-GC variant, also heap-dependent). The
  app drops the refs inside set_boxes -> synchronous mid-event-loop deletion.
fix: (NOT applied — diagnose-only mode. Directions below.)
  - Primary (lifetime): set_boxes must not let the old BoxItems' C++ objects
    die synchronously while the scene still holds pending updates. Retire the
    removed wrappers to a graveyard list released via QTimer.singleShot(0)
    (after the pending UpdateRequest flush), so the C++ deletion happens only
    after the updates referencing them are processed.
  - Defense-in-depth: guard TypesetOverlayItem.paint (box_item.py:331-334)
    with a shiboken validity check (Shiboken.isValid(self)) for the
    wrapper-alive/deleted-C++ variant; keep the existing None-pixmap guard.
  - Test-side (deferred-items suggestion): drain/clear scenes before Python
    GC in tests; add a regression test that drops the item refs before
    on_undo (mirroring the app) — exercises the synchronous-deletion path.
files_changed: [] (no source modified — diagnosis only)
