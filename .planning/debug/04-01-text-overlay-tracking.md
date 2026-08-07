---
status: diagnosed
trigger: "UAT Test 1 (04-UAT.md): text overlay is at a fixed image location, doesn't move with the box, doesn't scale with zoom, and 'just looks white' (outline not visible)"
created: 2026-08-06T00:00:00Z
updated: 2026-08-06T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — two independent root causes (RC-1 tracking/staleness; RC-2/RC-3 outline+clamp legibility). See Resolution.
test: offscreen Qt render probes reproducing the exact canvas code paths (setRect+_sync_handles move/resize; zoom render sweeps).
expecting: n/a — diagnosis complete (UAT gap mode: do NOT fix).
next_action: Return root-cause summary to orchestrator. Fix directions enumerated for planning.

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: |
  Text overlay (translucent white + 2px dark outline, z=120) sits INSIDE each box rect (border inset + 2px),
  tracks the box through move/resize/zoom (UI-SPEC §16, plan 04-04), scales with zoom (scene-units),
  and stays legible (outline visible) over light and dark artwork at 100-800% zoom (UAT test 1 truth).
actual: |
  1. Overlay text appears at a FIXED scene location regardless of box position.
  2. Overlay does not move with the box when dragged.
  3. Overlay appears not to scale with zoom; only "gets closer and further" relative to the box.
  4. Text "just looks white" — dark outline not visible; legibility unjudgeable.
errors: (none — silent behavioral failure)
reproduction: |
  Load a page, run OCR (Ctrl+R) so boxes carry recognized text; move a box (drag) or drag a TL/BL/TR
  resize edge; observe the text stays at its pre-move location, fully outside the box. Zoom in/out:
  the detached text drifts toward/away from the box. At fit-to-window zoom (<100%), no dark outline visible.
started: Plan 04-04 (overlay shipped with this defect; found at end-of-phase UAT, 2026-08-06).

## Eliminated

- hypothesis: "The text does not scale with zoom (QGraphicsTextItem transform issue / ItemIgnoresTransformations leak)."
  evidence: Offscreen render sweep: light-pixel count 942 (zoom 1) -> 4620 (zoom 2) -> 5907 (zoom 4) on the same
    text — the overlay is a NORMAL child (no ItemIgnoresTransformations) and scales with the view transform
    exactly like the box border. UI-SPEC §16 requires scene-units text scaling. The user's "doesn't scale
    much / gets closer and further" perception is the drift artifact of the DETACHED text (RC-1), compounded
    by the missing [10,28] viewport-px clamp (RC-3b: at fit-zoom ~0.3-0.5 the text renders ~4-7 device px,
    below the spec's own 10px floor).
  timestamp: 2026-08-06

- hypothesis: "The outline fails to render at all (setTextOutline unsupported by QGraphicsTextItem)."
  evidence: Render at zoom 1.0 shows 2710 dark (outline) pixels with darkest luminance 0 — setTextOutline DOES
    render. The invisibility is a sub-pixel width issue: 0 dark pixels at zoom 0.25, 260 at zoom 0.5.
    Cosmetic-pen variant also not honored by the text layout engine (78 vs 2277 dark px at 0.25 vs 1.0).
  timestamp: 2026-08-06

## Evidence

- timestamp: 2026-08-06
  checked: box_item.py:379-397 _sync_handles
  found: Repositions 4 handles + calls refresh_badge() only. NEVER refresh_text_overlay(). Docstring even documents
    "Also refreshes the bubble badge so it tracks the box" — overlay omitted.
  implication: The overlay is the ONLY BoxItem child not synced on geometry/zoom change.

- timestamp: 2026-08-06
  checked: box_item.py:442-478 refresh_text_overlay
  found: setPos(rect().x()+inset, rect().y()+inset) at line 477 is the ONLY overlay-position code in the codebase.
  implication: Overlay pos is in PARENT LOCAL coords, computed once per refresh from the CURRENT rect. Since the
    canvas moves boxes via setRect (changing rect x/y, item pos stays (0,0) — test_gui_boxes.py:772-802), a
    stale overlay stays at the OLD scene position forever until a content refresh.

- timestamp: 2026-08-06
  checked: canvas.py:1022-1023 (move), 1597-1598 + 1618-1619 (resize), 1452-1453 (zoom_changed)
  found: All three geometry paths call item.setRect(...) + item._sync_handles(). None touches the overlay.
  implication: Every drag-move and every left/top-edge resize leaves the overlay at the pre-change position.

- timestamp: 2026-08-06
  checked: Empirical probe (offscreen, real canvas code path)
  found: setRect(150,150,200,100)+_sync_handles(): overlay sceneBoundingRect (23,23,217,30), box (149,149,202,102)
    -> intersection area 0.0 (fully detached). refresh_text_overlay() restores (153,153). BR-only growth keeps
    x/y so the overlay coincidentally stays correctly inset; TL/BL/TR-edge drags and ALL moves break it.
  implication: RC-1 proven at the geometry level; exact user symptom ("text in one location on the image").

- timestamp: 2026-08-06
  checked: Empirical probe — badge tracking
  found: badge pos == sceneBoundingRect TL-outside target before AND after setRect+_sync_handles (tracks True).
  implication: refresh_badge in _sync_handles works; overlay is the sole untracked child.

- timestamp: 2026-08-06
  checked: Outline render sweep (2 scene-px pen) at zoom 0.25/0.5/0.75/1.0/2.0/4.0
  found: dark pixels 0 / 260 / 1059 / 2710 / 13566 / 47923. Pen renders at ~2*zoom device px.
  implication: RC-2 — below 100% zoom the outline is sub-pixel (0 at 0.25x). App default is fit-to-window
    (main_window.py:1009 fit_to_window on every page load; fit unclamped below 1.0) -> typical manga page in a
    window fits at ~0.3-0.5 -> outline invisible -> "just looks white" (85%-alpha near-white fill with no rim).

- timestamp: 2026-08-06
  checked: UI-SPEC §16 vs implementation
  found: Spec mandates a [10,28] viewport-px clamp for the overlay font ("Executor: clamp the rendered pixel
    size to min 10px / max 28px viewport-px across zoom") — NOT implemented (flat 14 scene px, box_item.py:104).
    Spec outline line "2px constant scene-px" IS implemented literally but fails the UAT legibility truth <100%.
  implication: RC-3b (missing clamp) contributes to tiny text at fit zoom; spec needs a deviation or
    reinterpretation for the outline to be zoom-constant (like badges/handles are viewport-px).

- timestamp: 2026-08-06
  checked: tests/test_gui_boxes.py + tests/test_gui_canvas.py coverage
  found: test_text_overlay_uses_outlined_text_format only asserts pen.style()!=NoPen and widthF()>=1.0 on the
    document format — never that the outline RENDERS. No test moves a box via setRect then asserts the overlay
    position/sceneBoundingRect; move tests (test_move_box_drag, test_boxitem_pos_and_rect_do_not_diverge_after_move)
    assert rect/current_box only. Canvas tests cover the T-toggle only.
  implication: TEST GAP — nothing would have caught RC-1 or RC-2; the fix needs regression tests.

## Resolution

root_cause: |
  THREE verified defects:

  RC-1 (symptoms 1+2 — fixed position / no tracking): the text-overlay child position is computed ONLY in
  refresh_text_overlay() (box_item.py:477, local-coords setPos from self.rect()), and no geometry/zoom path
  ever calls it. The canvas moves/resizes boxes via setRect (canvas.py:1022-1023, 1597-1598, 1618-1619) and
  syncs children via _sync_handles() (box_item.py:379-397), which refreshes handles + badge but NOT the
  overlay — so after a move (and any left/top-edge resize) the overlay stays at its ORIGINAL scene position,
  fully detached from the box (measured 0.0 overlap). Zoom (canvas.py:1452-1453) also only calls _sync_handles.
  refresh_text_overlay is only ever invoked on TEXT-content changes (Inspector/OCR/auto-number commits,
  inline-editor commit), so the staleness persists until text content changes. Badge comparison: refresh_badge
  IS in _sync_handles and uses sceneBoundingRect -> badge tracks correctly (verified).

  RC-2 (symptom 3 — "doesn't scale with zoom"): text DOES scale (verified — normal child, scene-units per
  spec §16). The perception is the RC-1 detachment: the stale text drifts toward/away from the box as zoom
  changes the on-screen separation, dominating the visual signal. Compounding: spec §16's [10,28] viewport-px
  font clamp is NOT implemented (flat 14 scene px), so at the app's default fit-zoom (~0.3-0.5 for a manga
  page; fit_to_window runs on every load, main_window.py:1009) the text renders ~4-7 device px — below the
  spec's own 10px readability floor.

  RC-3 (symptom 4 — "just looks white"): the 2px outline pen (_OVERLAY_OUTLINE, box_item.py:103) is in SCENE
  units and scales down with zoom: measured 2710 dark px at zoom 1.0 vs 260 at 0.5 vs 0 at 0.25 — sub-pixel
  and anti-aliased away below 100%. At the default fit-to-window zoom the dark legibility halo is invisible,
  leaving only the 85%-alpha near-white fill -> "just looks white" over light artwork, unjudgeable. The
  implementation matches spec §16's literal "2px constant scene-px" but fails the UAT truth ("legible over
  light and dark artwork at 100-800% zoom"); cosmetic pens are NOT honored by the text-outline renderer
  (verified) so the fix must scale the pen width with zoom.

fix: (NOT applied — diagnosis-only mode. Directions below.)
  - RC-1 fix site: box_item.py _sync_handles (line ~397) — add a reposition step for _text_overlay. Prefer
    splitting a lightweight _reposition_text_overlay() (setPos-only, from self.rect() + inset) out of
    refresh_text_overlay() and calling it from _sync_handles, because canvas.py:1023 runs _sync_handles on
    EVERY mouseMoveEvent during a drag and a full refresh_text_overlay (setPlainText + document rebuild)
    per mousemove would be wasteful. Single change covers move + resize + zoom (all funnel through
    _sync_handles).
  - RC-2 fix site: font-size clamp per spec §16 — re-apply overlay font as clamp(14*zoom, 10, 28)/zoom
    scene px on zoom change. Zoom value must flow in: _on_zoom_changed_reposition_handles (canvas.py:1445)
    currently discards its _zoom argument and only calls _sync_handles.
  - RC-3 fix site: outline pen width = 2/zoom scene px (constant 2 viewport px) applied on zoom change via
    the same refresh path (re-merge QTextCharFormat). This deviates from spec §16's "does not scale with
    zoom" line — needs a documented spec revision (the UAT truth is the acceptance contract).
  - Regression tests: (a) after setRect move + _sync_handles, overlay.sceneBoundingRect() is inside the box
    rect at the inset position; (b) same for TL-edge resize; (c) after zoom_changed emission, overlay stays
    inside + outline pen scales (if RC-3 fix lands); (d) keep the existing format assertions.
files_changed: [] (no source modified — diagnosis only)
verification: |
  All three root causes verified by direct offscreen measurement reproducing the exact canvas call paths
  (probe scripts in %TEMP%\overlay_verify.py, outline_verify.py, cosmetic_verify.py):
  - Move staleness: overlay/box intersection 0.0 after setRect+_sync_handles; fixed by refresh_text_overlay.
  - Scaling: text pixel area grows ~4.9x per 2x zoom (scales correctly).
  - Outline: 2710 / 260 / 0 dark pixels at zoom 1.0 / 0.5 / 0.25.
  - Badge: tracks move (correct control).
  - Cosmetic pen: not honored (78 vs 2277) — rejected fix approach.
---
