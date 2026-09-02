---
phase: quick-260901-wmn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/mask_editor.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/tools_strip.py
  - manga_ai_studio/gui/ocr_grab.py
  - manga_ai_studio/gui/assets/icons/ocr-grab.svg
  - manga_ai_studio/gui/main_window.py
  - tests/test_gui_tools_strip.py
  - tests/test_gui_ocr_grab.py
autonomous: true
requirements: [QUICK-260901-WMN]
user_setup: []

estimate:
  tokens: 70000
  raw_tokens: 35000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - Selecting the OCR Grab tool (strip button, S shortcut, or Tools menu) shows a small always-on-top floating history window and arms a fullscreen selection overlay; dragging a rectangle over ANY on-screen text captures it, runs manga-ocr, and copies the recognized text to the OS clipboard (Poricom behavior).
    - Every successful detection is prepended to the floating history window (most recent first, capped at 20 entries); clicking an entry re-copies its text.
    - The tool is screen-only: while active it never paints, mutates the mask, or alters page boxes; switching away from it hides the floating window and closes any open overlay.
    - OCR runs off the GUI thread through the existing TorchOCRModel / backend_factory / Worker pipeline (mirror of _dispatch_ocr_for_box), with the first-run model-download status message preserved; OCR failure shows the error chip, never a crash.
    - The tool follows the established tool contracts: 8th exclusive strip action + standalone window action + free-letter S shortcut, exactly one tool_changed emission per selection.
  artifacts:
    - ToolMode.OCR_GRAB in manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/gui/ocr_grab.py (ScreenGrabOverlay, OcrGrabHistoryPanel, grab_screen_region, qimage_to_rgb_array)
    - ocr-grab.svg + 8th ToolsStrip button/action in manga_ai_studio/gui/tools_strip.py
    - action_tool_ocr_grab + _start_ocr_grab_session/_run_ocr_grab_task/_on_grab_region_selected/_on_ocr_grab_finished/_on_ocr_grab_error in manga_ai_studio/gui/main_window.py
    - New tests in tests/test_gui_ocr_grab.py + 8th-tool assertions in tests/test_gui_tools_strip.py
  key_links:
    - tools_strip.action_ocr_grab -> MainWindow.set_active_tool(OCR_GRAB) -> ocr_grab_panel.show + _start_ocr_grab_session (ScreenGrabOverlay)
    - ScreenGrabOverlay.region_selected -> grab_screen_region(screen, rect) -> qimage_to_rgb_array -> Worker(_run_ocr_grab_task) -> model.recognize (TorchOCRModel singleton)
    - _on_ocr_grab_finished -> QGuiApplication.clipboard().setText + OcrGrabHistoryPanel.add_entry
---

<objective>
Add an "OCR Grab" tool (Poricom-style): the user selects the tool, drags a rectangle over ANY text on the screen (manga reader, browser, anywhere), and the app captures that screen region, runs manga-ocr on it, and copies the recognized text to the OS clipboard. A small always-on-top floating window — visible while the tool is selected — lists the recent detections; clicking an entry re-copies it.

Purpose: today OCR only works on boxes drawn on the loaded page. This tool decouples OCR from the document entirely: quick lookups of Japanese text visible anywhere on screen, with a re-copyable history.

Output: Working 8th exclusive strip tool, end-to-end (ToolMode enum -> strip/menu/shortcut -> fullscreen overlay -> screen grab -> Worker OCR -> OS clipboard -> floating history), with tests. All interpreter invocations use the pinned interpreter from AGENTS.md (`"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest ...`).
</objective>

<execution_context>
@$HOME/.zcode/gsd-core/workflows/execute-plan.md
@$HOME/.zcode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/core/mask_editor.py
@manga_ai_studio/gui/canvas.py
@manga_ai_studio/gui/tools_strip.py
@manga_ai_studio/gui/main_window.py
@manga_ai_studio/adapters/torch_impl.py
@manga_ai_studio/gui/worker_thread.py
@tests/test_gui_tools_strip.py
@tests/test_gui_canvas.py

Key verified anchors (line numbers from planning probe; re-grep if drifted):
- ToolMode enum: mask_editor.py:56 (MOVE/BRUSH/RECTANGLE/LASSO/ERASER/RESTORE/CROP). PAINT_TOOLS frozenset: canvas.py:105.
- Canvas left-press gate: canvas.py:1549-1554 — paint begins only when `current_tool not in (ToolMode.MOVE, ToolMode.CROP)` AND a mask exists; the crop-arm branch above it is gated on `== ToolMode.CROP` only. `_update_cursor_visuals` (canvas.py:1206 area) hides the brush dot for non-PAINT_TOOLS automatically.
- ToolsStrip: tools_strip.py — `_TOOL_ICONS` :44-52, seven `_make_tool_action` defs :128-171, `_action_to_tool` :174-182, checkable-buttons loop :194-202, `_make_tool_action` :247-268, `set_active_tool` :285, `active_tool()` :307. The strip's QActionGroup is exclusive and holds EXACTLY the strip's own tool actions (WR-02).
- MainWindow: `action_tool_crop` block :1070-1077, `action_tool_restore` block :1089-1097 (standalone checkable window actions, NOT in the strip group — WR-02), Tools menu addActions :1171-1172, `_refresh_action_states` page-open gating tuple includes action_tool_restore/crop at :1374-1375, tool QShortcut loop ("V","B","R","L","E","O","G") :3676-3686, `set_active_tool` :5115 with the window-action sync tuple :5140-5148.
- OCR pipeline to mirror: `_dispatch_ocr_for_box` ~:6642 (backend_factory -> Worker -> _op_running gate -> indeterminate progress -> first-run `is_ocr_downloaded()` status note), `_run_ocr_task` ~:6703 (model.load(self._resolve_ocr_model_path(), device="auto") then model.recognize(region) — NO Qt in the worker body, T-01-07), `_resolve_ocr_model_path` ~:6580, TorchOCRModel (torch_impl.py:288: load() lazy singleton, recognize(np.ndarray RGB uint8) -> str, "Model not loaded" guard).
- Worker: worker_thread.py WorkerSignals (result/error/finished) — connect result -> _on_ocr_grab_finished, error -> _on_ocr_grab_error, finished -> cleanup.
- Payload discipline: numpy/QImage crossing a Qt signal or thread boundary must be `.copy()`-detached (RESEARCH Pitfall 2; tests/test_payload_aliasing.py). QImage rows may be stride-padded — use `bytesPerLine`-aware conversion, never assume w*3.
- Shortcuts audit: bare-letter registrations are V B R L E O G M T P D C F — "S" is free (mnemonic: Screen).
- Multi-monitor: launch the overlay on `self.screen()` (the screen MainWindow lives on); `QScreen.grabWindow(0)` grabs that screen; scale the selection rect by `screen.devicePixelRatio()` before cropping (Windows HiDPI).
- Test patterns: `_window(qtbot, tmp_path)` helper + strip-button enumeration in tests/test_gui_tools_strip.py; MainWindow tool-shortcut assertions at tests/test_gui_canvas.py:525 (`test_main_window_tool_shortcuts`); pytest.ini marks `gui` for pytest-qt tests.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Register the 8th tool — ToolMode.OCR_GRAB, strip button, window action, S shortcut, canvas no-op (+ tests)</name>
  <files>manga_ai_studio/core/mask_editor.py, manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/tools_strip.py, manga_ai_studio/gui/assets/icons/ocr-grab.svg, manga_ai_studio/gui/main_window.py, tests/test_gui_tools_strip.py, tests/test_gui_ocr_grab.py</files>
  <action>
1. mask_editor.py: add `OCR_GRAB = "ocr_grab"` to ToolMode (last member, after CROP) and extend the class docstring: the 8th tool is a SCREEN-grab OCR tool (Poricom-style) — it never touches the mask planes, the working image, or the page boxes; its interaction surface is a fullscreen overlay handled by MainWindow, and the canvas treats it as inert.
2. canvas.py: in the left-press paint gate (canvas.py:1549-1554), change the exclusion tuple from `(ToolMode.MOVE, ToolMode.CROP)` to `(ToolMode.MOVE, ToolMode.CROP, ToolMode.OCR_GRAB)` so a press on the page with the grab tool active falls through to `super().mousePressEvent` (Move/Pan-style inert behavior). Nothing else in the canvas changes: PAINT_TOOLS is untouched (no brush-dot cursor), the crop branch is already CROP-only, and box hit-test/select on press remains harmless.
3. Create `manga_ai_studio/gui/assets/icons/ocr-grab.svg` mirroring the existing icon format (24x24 viewBox, stroke #e8e8ea, stroke-width 2, round caps/joins, fill none) with a minimal viewfinder glyph: four corner brackets and a short horizontal text line inside.
4. tools_strip.py: add `ToolMode.OCR_GRAB: "ocr-grab"` to `_TOOL_ICONS`; create `self.action_ocr_grab` via `_make_tool_action` with tooltip "OCR Grab tool (S) — drag a rectangle over any on-screen text; the recognized text is copied to the clipboard."; add it to `_action_to_tool`, the checkable-buttons loop (place it after Crop — screen tools last, after the canvas-geometry tools), and keep the group exclusive (it now holds exactly eight actions). Update the class docstring button count.
5. main_window.py — follow the Restore/Crop window-action precedent exactly:
   - `action_tool_ocr_grab` QAction block after the `action_tool_restore` block (:1089-1097): text "OCR Grab", checkable, setData(ToolMode.OCR_GRAB), triggered -> set_active_tool(ToolMode.OCR_GRAB) via the same lambda pattern, tooltip matching the strip copy.
   - `tools_menu.addAction(self.action_tool_ocr_grab)` after the Crop entry (:1172).
   - Do NOT add `action_tool_ocr_grab` to the `_refresh_action_states` page-open gating tuple (:1374-1375) — this tool works with NO page open (it is a screen tool, not a page tool). Leave gating lists untouched.
   - `set_active_tool` sync tuple (:5140-5148): add `self.action_tool_ocr_grab`.
   - Shortcut loop (:3676-3686): add `("S", ToolMode.OCR_GRAB)`.
   - Do NOT add any session logic yet (Task 3 owns `_start_ocr_grab_session`); after this task `set_active_tool(OCR_GRAB)` only syncs strip/menu/shortcut state.
6. Tests:
   - tests/test_gui_tools_strip.py: update the button-count/enumeration assertions to 8 tool buttons; new case: `strip.set_active_tool(ToolMode.OCR_GRAB)` -> `active_tool()` returns OCR_GRAB, the ocr-grab action is checked and all others unchecked, exactly one `tool_changed` emission carrying ToolMode.OCR_GRAB (qtbot signal spy, existing single-emission pattern); the button's icon is non-null (icon lives on the action, D-06).
   - New tests/test_gui_ocr_grab.py (start the file with the same importorskip/gui-mark pattern): ToolMode.OCR_GRAB exists and stringifies "ocr_grab"; MainWindow has `action_tool_ocr_grab`, it is checkable, lives in the Tools menu, and triggering it makes `window.tools_strip.active_tool() == ToolMode.OCR_GRAB` with the window action checked; the S shortcut activates it (mirror test_main_window_tool_shortcuts); canvas inertness — load an image into a canvas, `set_tool(ToolMode.OCR_GRAB)`, synthesize a left-press+release on the canvas (reuse the `_press`/`_release` helper pattern from tests/test_gui_canvas.py), assert no paint occurred (mask unchanged / `_is_painting` never set) and no crop state was armed.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_tools_strip.py tests/test_gui_ocr_grab.py -x -q</automated>
  </verify>
  <done>ToolMode.OCR_GRAB registered everywhere the other 7 tools are (enum, strip icon+action+button, window action, Tools menu, S shortcut, set_active_tool sync); the canvas treats it as inert; the strip group holds exactly 8 exclusive actions; all strip + new tests pass.</done>
</task>

<task type="auto">
  <name>Task 2: New gui/ocr_grab.py — ScreenGrabOverlay, OcrGrabHistoryPanel, screen-grab + pixel conversion helpers (+ unit tests)</name>
  <files>manga_ai_studio/gui/ocr_grab.py, tests/test_gui_ocr_grab.py</files>
  <action>
Create `manga_ai_studio/gui/ocr_grab.py` with four public pieces (pure widgets + functions, NO main_window imports, NO OCR/model imports — the module stays importable headless):

1. `ScreenGrabOverlay(QWidget)`: fullscreen screen-selection rubber-band overlay, Poricom-style.
   - Constructor takes a `QScreen`. Window flags: FramelessWindowHint + WindowStaysOnTopHint + Qt.Tool; setGeometry(screen.geometry()); WA_TranslucentBackground; CrossCursor. Keep a module-level dim color rgba(0,0,0,~90) and a selection border in the accent #00d4ff (strip-highlight token).
   - mousePress on LeftButton starts the rubber band from that point; mouseMove updates it; mouseRelease emits `region_selected(QRect)` (normalized — negative drags normalized to positive w/h) and closes. Esc (keyPressEvent) emits `selection_cancelled` and closes. Show via `show()` (geometry already fullscreen) — never modal exec (the panel must stay interactive).
   - paintEvent: dim the whole overlay, then fill ONLY outside the current selection darker and stroke the selection rect in accent while dragging; nothing selected yet = plain dim.
   - The overlay NEVER stores or returns grabbed pixels — it is only a rect picker (keeps it trivially testable offscreen).
2. `grab_screen_region(screen: QScreen, rect: QRect) -> QImage` (module function): `pixmap = screen.grabWindow(0)`, `image = pixmap.toImage()`, compute the crop rect scaled by `screen.devicePixelRatio()` (multiply x/y/w/h, round to ints, intersect with the image bounds), return `image.copy(crop).convertToFormat(QImage.Format.Format_RGB888)`. Guard: an empty/degenerate rect returns a null QImage.
3. `qimage_to_rgb_array(image: QImage) -> np.ndarray`: stride-safe RGB uint8 conversion — allocate from `image.constBits()` sized `image.sizeInBytes()`, reshape to (h, image.bytesPerLine()), slice to w*3, reshape (h, w, 3), and return a detached `.copy()` (Pitfall 2 payload discipline; bytesPerLine padding on Windows makes the naive flat reshape wrong).
4. `OcrGrabHistoryPanel(QWidget)`: the small floating history window.
   - Window flags: Qt.Tool + WindowStaysOnTopHint + FramelessWindowHint-free (a titled small window is fine); fixed compact size (~280x360); title "OCR Grab".
   - Members: a QListWidget (most recent first), a "New capture" button, and a small hint label ("Click an entry to re-copy — S or New capture for another grab").
   - Signals: `capture_requested()` (button), `entry_copy_requested(str)` (item activated/clicked — carries the entry's full text; store full text on the item's data role, display a truncated one-line preview).
   - `add_entry(text: str)`: prepend, cap the list at MAX_HISTORY = 20 (drop from the tail), skip empty/whitespace text; `entries() -> list[str]` accessor for tests (most recent first).
   - The panel holds NO business logic — no clipboard writes, no OCR calls; it only emits signals (mirror the InspectorPanel pure-follower precedent, plan 04-04).

Tests in tests/test_gui_ocr_grab.py (pytest-qt, mark gui):
- Overlay: `qtbot` + synthetic mouse events (QMouseEvent, the existing 5-arg ctor pattern from tests/test_gui_canvas.py) — press/move/release emits exactly one `region_selected` with the normalized rect and the widget closes; an Esc keypress emits `selection_cancelled` and closes; a click without drag emits a degenerate rect (caller decides — Task 3 ignores <1px).
- qimage_to_rgb_array: build a known 4x3 QImage (Format_RGB888 with deliberately padded bytesPerLine), assert shape (3,4,3), dtype uint8, exact pixel values, and that mutating the array does not mutate the QImage (detached).
- grab_screen_region: monkeypatch-stub at the QScreen level is flaky — instead test the DPR math and bounds intersection on a fabricated image by factoring the crop math into a small pure helper (`_crop_scaled(image, rect, dpr) -> QImage`) and unit-testing THAT; grab_screen_region itself gets one live smoke test (primary screen, 1x1 rect) that only asserts a non-null return.
- Panel: add_entry prepends (most recent first), entries() round-trips, cap at 20 enforced, empty text rejected; entry_copy_requested carries the full text; capture_requested fires from the button.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_ocr_grab.py -x -q</automated>
  </verify>
  <done>gui/ocr_grab.py provides the overlay (rect picker with Esc cancel), the DPR-safe grab + detached numpy conversion helpers, and the pure-follower history panel; all module tests pass headless-with-Qt.</done>
</task>

<task type="auto">
  <name>Task 3: MainWindow wiring — session lifecycle, Worker OCR dispatch, clipboard copy, history updates (+ tests)</name>
  <files>manga_ai_studio/gui/main_window.py, tests/test_gui_ocr_grab.py</files>
  <action>
Wire the tool end-to-end in main_window.py, mirroring `_dispatch_ocr_for_box` (~:6642) throughout:

1. Construction (near the other panel/dock construction): create `self.ocr_grab_panel = OcrGrabHistoryPanel(self)`; connect `capture_requested` -> `_start_ocr_grab_session` and `entry_copy_requested` -> a one-line slot that calls `QGuiApplication.clipboard().setText(text)` and flashes the status bar ("Copied from history"). The panel is created hidden; it must NOT appear at startup.
2. Session lifecycle in `set_active_tool` (:5115): after the existing sync code, branch —
   - If `tool == ToolMode.OCR_GRAB`: show + raise `ocr_grab_panel`, then call `self._start_ocr_grab_session()` (both on fresh selection AND re-selection while already active — pressing S again starts a new grab; this is the re-trigger path).
   - If the PREVIOUS tool was OCR_GRAB and the new one differs: hide `ocr_grab_panel` and close any live overlay (`_close_grab_overlay()`). Track the previous tool in a private attribute.
3. `_start_ocr_grab_session()`: close any existing overlay first (one session at a time); build a new `ScreenGrabOverlay(self.screen())`; connect `region_selected` -> `_on_grab_region_selected`, `selection_cancelled` -> `_close_grab_overlay`; keep a reference `self._ocr_grab_overlay`; show it.
4. `_on_grab_region_selected(rect: QRect)`: close the overlay FIRST (before any grab — the overlay must never appear in its own capture); then: if rect is degenerate (w or h < 1) flash a status hint and return; grab pixels on the main thread via `grab_screen_region(self.screen(), rect)`; convert with `qimage_to_rgb_array` (detached); guard a null image (return with status hint); then dispatch.
5. Dispatch + worker (mirror `_dispatch_ocr_for_box` exactly): `_op_running` gate (skip with a status note if an op is running — no worker pileup, T-4-14 pattern); `model = backend_factory("ocr", self._ocr_backend())`; `worker = Worker(self._run_ocr_grab_task, region_arr, model)`; connect result/error/finished; `setAutoDelete(True)`; set `_op_running`, `_refresh_action_states()`, hide the error chip, indeterminate progress bar, status "Recognizing screen text…" with the first-run note (import `is_ocr_downloaded` from `panelcleaner.model_downloader` inside the method, CR-11 pattern); start on `QThreadPool.globalInstance()`.
6. `_run_ocr_grab_task(self, region_arr, model, progress_callback=None, abort_flag=None) -> dict`: numpy/adapter only — `model.load(self._resolve_ocr_model_path(), device="auto")` (singleton, load-once) then `return {"text": model.recognize(region_arr), "source": "screen_grab"}`. NO Qt calls in this body (T-01-07).
7. `_on_ocr_grab_finished(result: dict)`: extract text; empty/whitespace text -> status "No text recognized" and NO clipboard write, NO history entry, then fall through to cleanup; otherwise `QGuiApplication.clipboard().setText(text)` (OS clipboard — this IS the feature; the canvas box-copy's deliberate no-OS-clipboard rule does not apply here), `ocr_grab_panel.add_entry(text)`, status "Copied {n} chars to clipboard".
8. `_on_ocr_grab_error(worker_error)`: mirror `_on_ocr_error` (log the traceback, show the error chip with a friendly message) — an OCR failure never crashes the session, and the panel stays open for another grab.
9. Cleanup (`_on_ocr_grab_cleanup`, connected to worker.signals.finished): `_op_running = False`, hide the progress bar, `_refresh_action_states()` — mirror `_on_ocr_cleanup`. Do NOT auto-relaunch the overlay: after each capture the user decides (S, New capture, or switching tools).

Tests appended to tests/test_gui_ocr_grab.py (pytest-qt):
- Handler unit: clear the clipboard to a sentinel, call `window._on_ocr_grab_finished({"text": "テスト", "source": "screen_grab"})` directly -> clipboard text is "テスト", `window.ocr_grab_panel.entries()[0] == "テスト"`, status mentions copied; empty-text result -> clipboard unchanged, entries() empty.
- Dispatch integration with stubs: monkeypatch `MainWindow._run_ocr_grab_task` to return a fixed dict and monkeypatch `manga_ai_studio.gui.ocr_grab.grab_screen_region` to return a small synthetic QImage — build the window with `window._start_ocr_grab_session` stubbed (no overlay during construction), set the tool via `set_active_tool(ToolMode.OCR_GRAB)`, then drive `_on_grab_region_selected(QRect(10, 10, 120, 40))`; qtbot.waitUntil the clipboard/history show the stub text and `_op_running` is False again.
- Session lifecycle: with `_start_ocr_grab_session` NOT stubbed, `set_active_tool(OCR_GRAB)` shows the panel and creates a live overlay; switching to `ToolMode.MOVE` hides the panel and closes the overlay; re-selecting OCR_GRAB starts a NEW overlay instance (the old one closed).
- Re-copy from history: two entries in the panel; activate the older one -> clipboard carries the older text.
- Error path: connect-free — call `_on_ocr_grab_error` with a constructed WorkerError and assert the error chip is visible and `_op_running` False after cleanup.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_ocr_grab.py tests/test_gui_tools_strip.py -x -q</automated>
  </verify>
  <done>Selecting OCR Grab shows the floating history + fullscreen overlay; a dragged rect grabs the screen, OCRs off-thread through the existing pipeline, copies the recognized text to the OS clipboard, and prepends it to the history (capped, click-to-re-copy); Esc/tool-switch closes the overlay; errors surface via the error chip; full targeted suite passes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| screen -> app | grabWindow reads whatever pixels are on the user's screen (any application) |
| OCR result -> OS clipboard | recognized text is published system-wide |
| fullscreen overlay | a topmost window intercepting all input while active |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QG-01 | Information Disclosure | ScreenGrabOverlay / grab_screen_region | low | accept | User-initiated capture of a user-chosen region; pixels are converted in-memory, never written to disk or session state; overlay closes before the grab so it cannot photograph itself |
| T-QG-02 | Information Disclosure | clipboard copy in _on_ocr_grab_finished | low | accept | Publishing recognized text to the OS clipboard is the feature itself (Poricom parity); the canvas box-copy no-OS-clipboard rule is scoped to in-app box duplication and deliberately does not extend here |
| T-QG-03 | Denial of Service | overlay lifecycle | low | mitigate | Single-session rule (`_close_grab_overlay` before any new session), Esc cancel, tool-switch close, and overlay close on capture — no stuck topmost window can block the desktop |
| T-QG-SC | Tampering | dependencies | low | accept | No new packages: reuses PySide6, numpy, manga-ocr, and the vendored model_downloader already in the environment |
</threat_model>

<verification>
- `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_ocr_grab.py tests/test_gui_tools_strip.py tests/test_gui_canvas.py -x -q` (targeted; canvas regression for the gate-tuple edit).
- Full suite: `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` (baseline 1214 passed; must not regress).
- Manual smoke (operator, real display): launch via start.bat, press S, drag over some Japanese text in another window, confirm the clipboard receives the recognized text and the floating window lists it; press Esc mid-drag to cancel; click a history entry to re-copy.
</verification>

<success_criteria>
- OCR Grab is the 8th exclusive strip tool with icon, tooltip, Tools menu entry, and free-letter S shortcut; one tool_changed emission per selection via every entry path.
- Screen-region capture -> manga-ocr -> OS clipboard works end-to-end, fully off the GUI thread, with first-run model-download messaging preserved.
- Floating always-on-top history window appears only while the tool is active, lists up to 20 detections (most recent first), and re-copies on click.
- The page canvas is untouched while the tool is active; switching tools hides the panel and closes the overlay.
- No regression in the existing suite (1214-pass baseline).
</success_criteria>

<output>
Create `.planning/quick/260901-wmn-add-a-new-tool-to-the-app-similar-to-wha/260901-wmn-SUMMARY.md` when done
</output>
