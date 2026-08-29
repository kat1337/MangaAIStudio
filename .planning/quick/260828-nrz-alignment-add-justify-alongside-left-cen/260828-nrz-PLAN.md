---
phase: quick-260828-nrz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/text_style.py
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/gui/inspector_panel.py
  - tests/test_core/test_text_style.py
  - tests/test_core/test_typeset_layout.py
  - tests/test_gui_inspector_styling.py
autonomous: true
requirements: [QUICK-260828-NRZ]
estimate:
  tokens: 45000
  raw_tokens: 45000
  tasks: 2
  confidence: low
must_haves:
  truths:
    - A text box with align_h "justify" renders with every line except the last stretched flush to both inner edges (normal text editor justification); the last line keeps its natural alignment.
    - Justify measurement and render use the SAME document, so fit/overflow/ink read honest geometry (no measurement drift).
    - Vertical (tategaki) boxes with align_h "justify" distribute >= 2 columns across the full inner width; a single column behaves exactly as today (center).
    - The Inspector Align combo shows Left/Center/Right/Justify, loads "justify" from a style, commits it through style_align_changed, and Mixed-sentinel handling still works.
    - "justify" round-trips through TextStyle.to_dict/from_dict; genuinely unknown align_h values still fall back to "center" (V5 gate intact).
  artifacts:
    - manga_ai_studio/core/text_style.py — _ALIGN_H_VALUES gains "justify"
    - manga_ai_studio/gui/text_renderer.py — justify branch in horizontal layout + vertical column distribution
    - manga_ai_studio/gui/inspector_panel.py — display map, combo items, mixed lists, _select_combo learn Justify
    - tests/test_core/test_text_style.py — justify V5 acceptance + unknown-fallback
    - tests/test_core/test_typeset_layout.py — horizontal justify flush-line probe + vertical column distribution
    - tests/test_gui_inspector_styling.py — combo item, load, Mixed, signal payload
  key_links:
    - Inspector _ALIGN_H_DISPLAY["justify"] -> combo "Justify" -> style_align_changed payload "justify" -> main_window._replace_align -> TextStyle.align_h -> renderer _ALIGN_H_TO_QT["justify"]
    - layout() justify branch: raw (un-pre-broken) text + WrapAtWordBoundaryOrAnywhere document, and that same doc instance is both measured and returned in LayoutResult.document
---

<objective>
Add "justify" as a fourth horizontal alignment (alongside left/center/right) that behaves like a normal text editor's justified text: lines stretch to fill the box width, last line keeps its natural alignment. Covers the model (V5 serialization), the horizontal renderer, the vertical (tategaki) renderer, and the Inspector combo — end to end.

Purpose: scanlation typesetting wants newspaper-style justified blocks; today only left/center/right exist.

Output: committed code + tests; full suite green under the pinned interpreter.
</objective>

<execution_context>
@C:\Users\Stella\.zcode\gsd-core\workflows\execute-plan.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md

Design decision (locked for this task): **Approach (A) — natural-wrap Qt justification.**
For align_h="justify", layout() skips the owned breaker (core/text_wrap) and passes the RAW
text to _build_document at its DEFAULT wrap mode (WrapAtWordBoundaryOrAnywhere) with
AlignJustify in the QTextOption. Qt justifies every line except the last natively.
Rejected: per-word placement painting (approach B) — it would touch the paint path,
effects/glow silhouettes, and measurement parity; far more invasive for the same result.
Because measurement==render already holds (the doc measured by the fit loop IS the doc
returned in LayoutResult.document), approach A needs zero parity work.

Vertical decision: justify = distribute columns evenly across inner_w by stretching the
inter-column gaps when there are >= 2 columns; a single column falls back to the existing
center behavior. Implemented in the dx-block arithmetic only — the x-flow loop consumes an
effective per-column gap.

Pinned interpreter (AGENTS.md): "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe"
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Model + renderer justify (horizontal natural-wrap path, vertical column distribution) + core tests</name>
  <files>manga_ai_studio/core/text_style.py, manga_ai_studio/gui/text_renderer.py, tests/test_core/test_text_style.py, tests/test_core/test_typeset_layout.py</files>
  <behavior>
    - TextStyle.from_dict({"align_h": "justify"}).align_h == "justify" (V5 accepts the new value)
    - TextStyle.from_dict({"align_h": "diagonal"}).align_h == "center" (unknown still falls back — existing test stays green)
    - to_dict -> from_dict round-trip preserves align_h="justify"
    - Horizontal layout (manual size, multi-line text that wraps): with align_h="justify", every line_rect except the last spans inner_w within a 2 px tolerance; the last line is narrower than inner_w (natural); ink stays inside the inner rect
    - Horizontal layout with align_h="justify" and single-line text: renders as today (no stretch of the last/only line)
    - Overflow flag: a justified block too tall for the box still reports overflow honestly (height-only fit in justify mode)
    - layout_vertical placements with align_h="justify" and text producing >= 2 columns: first column's right edge at inner_w (within 0.5 px), last column's left edge at 0 (within 0.5 px)
    - layout_vertical with align_h="justify" and a single column: same x as align_h="center" (fallback semantics)
  </behavior>
  <action>
    1. core/text_style.py — extend _ALIGN_H_VALUES (line ~72) to ("left", "center", "right", "justify"). Update the align_h field docstring (line ~157) to list "justify". Do NOT touch the from_dict V5 gate (lines ~247-249): membership-in-tuple already admits "justify" and still rejects garbage to "center". to_dict (line ~206) passes the field through — no change needed there.
    2. gui/text_renderer.py, horizontal:
       a. Add "justify": Qt.AlignmentFlag.AlignJustify to _ALIGN_H_TO_QT (line ~115).
       b. In layout()'s manual-size branch (~line 745): when style.align_h == "justify", skip _break_lines_for and call _build_document with the RAW text and its DEFAULT wrap argument (omit wrap= — the default WrapAtWordBoundaryOrAnywhere is the natural-wrap mode). Keep the overflow check (doc height vs inner_h) unchanged. Add a brief comment: the owned breaker's NoWrap pre-breaking would defeat AlignJustify (nothing to stretch in single-line blocks), so justify uses Qt's native natural wrap.
       c. In the auto-fit loop (~line 783): when justify, do not call _break_lines_for — set the split_latin contributor to False (there is no owned-breaker Latin-split signal; the fit predicate degrades to height-only, per the locked approach-A decision) and build the candidate doc from the raw text with the default wrap. Keep every other loop mechanic (grow cap, shrink budget, floor check, last-fit retention) byte-identical.
    3. gui/text_renderer.py, vertical — _vertical_placements dx section (~line 563-584): after col_widths/block_w are computed, when style.align_h == "justify" and len(columns) >= 2, distribute the slack: an effective per-column gap = char_gap + (inner_w - block_w) / (len(columns) - 1), with block_w becoming inner_w and dx_block = 0.0; a single justify column takes the existing center branch unchanged. The existing x-flow loop (x starts at dx_block + block_w, decrements gap then column width) consumes the effective gap as-is — no other edits. Overflow semantics stay honest because the stretched block_w == inner_w exactly.
    4. Tests, tests/test_core/test_text_style.py — extend test_align_values_validated with the justify acceptance assertion; add a round-trip assertion for justify in the existing round-trip test.
    5. Tests, tests/test_core/test_typeset_layout.py — add a horizontal justify test next to test_align_h_shifts_ink_rect (manual size, text long enough to wrap into >= 3 lines, probe result.line_rects widths as in the behavior block), and a vertical justify test next to test_vertical_centering_and_alignment (text long enough for >= 2 columns, probe first/last column edges; plus the single-column-equals-center assertion). Use the existing qapp fixture and TextStyle(font_size_px=..., auto_fit=False) pattern.
    Commit: feat(quick-260828-nrz): add justify horizontal alignment to model + renderer
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_style.py tests/test_core/test_typeset_layout.py -x -q</automated>
  </verify>
  <done>All model + typeset layout tests pass including the new justify assertions; unknown align_h still falls back to center; justify renders flush-justified lines with an honest overflow flag and distributes vertical columns.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Inspector Align combo gains Justify (display map, items, Mixed, load/commit) + GUI tests</name>
  <files>manga_ai_studio/gui/inspector_panel.py, tests/test_gui_inspector_styling.py</files>
  <behavior>
    - _ALIGN_H_DISPLAY maps "justify" -> "Justify" (and _ALIGN_H_TO_MODEL derives "Justify" -> "justify" automatically via the existing comprehension)
    - align_combo item list is ["Left", "Center", "Right", "Justify"] — existing indices (0=Left, 1=Center, 2=Right) unchanged so current tests stay green
    - Loading a style with align_h="justify" shows "Justify" in the combo (no Mixed sentinel)
    - Selecting "Justify" on a loaded box emits style_align_changed("justify", <v>) — commit path needs zero edits beyond the display map
    - Mixed-state list includes "Justify" among the real items; "Mixed" still maps to the None untouched-axis sentinel
  </behavior>
  <action>
    1. gui/inspector_panel.py — four list sites + one map, nothing else:
       a. _ALIGN_H_DISPLAY (line ~201): add "justify": "Justify". (_ALIGN_H_TO_MODEL and _ALIGN_H_DISPLAY-derived maps update automatically.)
       b. align_combo.addItems (line ~547): ["Left", "Center", "Right", "Justify"].
       c. Mixed-sentinel list at line ~877 (real-items list) and line ~882 (leading-Mixed list): append "Justify" to each.
       d. _select_combo call for align_h (line ~1001): pass the four-item display list.
    2. The commit path (_commit path reading currentText into _ALIGN_H_TO_MODEL, ~line 1566-1583) requires NO changes — verify by reading it once; WR-01 no-op and WR-02 both-None guards already handle the new value generically.
    3. main_window._replace_align passes align_h through to dataclasses.replace — no change (grep-verified: generic dict-changes path).
    4. Tests, tests/test_gui_inspector_styling.py — follow the existing patterns: assert "Justify" is in panel.align_combo's items; extend the load test (style align_h="justify" -> currentText "Justify"); extend the Mixed test's item expectations; add a signal assertion setCurrentIndex(3) emits ("justify", "middle") mirroring the existing Left-commit test at line ~258.
    5. Full-suite regression run (other files grep-assert align_h values only from the left/center/right set, so they are unaffected — confirm with the run).
    Commit: feat(quick-260828-nrz): expose Justify in the Inspector align combo
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_inspector_styling.py -x -q && "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>Inspector offers and commits Justify end to end (load, Mixed, signal payload "justify"); the full pinned-interpreter suite passes with zero regressions.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| project file -> TextStyle.from_dict | Untrusted align_h string from saved JSON crosses the V5 validation gate |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QN-01 | Tampering | TextStyle.from_dict align_h gate | low | mitigate | Membership check against _ALIGN_H_VALUES (now 4 values) — anything else falls back to "center"; regression-tested via the unknown-fallback assertion |
</threat_model>

<verification>
- Pinned-interpreter run: tests/test_core/test_text_style.py, tests/test_core/test_typeset_layout.py, tests/test_gui_inspector_styling.py all green
- Full suite green (baseline ~1214 passed)
- grep "justify" in manga_ai_studio/core/text_style.py, manga_ai_studio/gui/text_renderer.py, manga_ai_studio/gui/inspector_panel.py shows the model value, renderer map/branches, and inspector map/items respectively
</verification>

<success_criteria>
- A user picks "Justify" in the Inspector and the box renders newspaper-justified text (lines flush both edges, last line natural) in horizontal mode
- Vertical boxes justify by distributing columns across the full inner width; single column unchanged
- justify saves/loads through the project file; corrupt values degrade to center
- No behavioral change for left/center/right (existing tests untouched and green)
</success_criteria>

<output>
Report completion to the orchestrator; the orchestrator commits docs artifacts. Executor commits code + tests only (two atomic commits, one per task).
</output>
