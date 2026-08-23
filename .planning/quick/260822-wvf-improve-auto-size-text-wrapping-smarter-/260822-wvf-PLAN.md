---
phase: quick-260822-wvf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/text_wrap.py
  - manga_ai_studio/gui/text_renderer.py
  - tests/test_core/test_text_wrap.py
  - tests/test_core/test_typeset_layout.py
autonomous: true
requirements: [QUICK-WRAP-01]

estimate:
  tokens: 48000
  raw_tokens: 32000
  tasks: 3
  confidence: med

must_haves:
  truths:
    - "Contractions like can't / don't never split across lines in the committed render (overlay AND bake)"
    - "Punctuation like ? ! , never starts a line — 'Are you free ?' breaks before 'free ?', not after"
    - "Lines are balanced: no one-word orphan last line when a better break exists; no one-word widow first line"
    - "Oversized single atoms (long CJK runs / URLs) still char-split so nothing overflows inner_w"
    - "Vertical (tategaki) rendering is byte-for-byte unaffected"
  artifacts:
    - manga_ai_studio/core/text_wrap.py
    - tests/test_core/test_text_wrap.py
    - Updated text_renderer.layout() using pre-broken lines + NoWrap on both manual and auto-fit paths
  key_links:
    - core/text_wrap.break_lines consumed by gui/text_renderer.layout() via QFontMetricsF.horizontalAdvance measured at the SAME rounded pixelSize the document renders (_style_font)
    - _build_document wrap-mode seam (NoWrap for pre-broken lines)
---

<objective>
Replace Qt's greedy word-wrap with owned line breaking (tokenizer + Knuth-Plass-lite DP) so auto-size typeset text never produces orphan/fragment lines like `can/'t`, `don'/t`, or `Are/you/free/?`.

Purpose: The shared `layout()` seam (gui/text_renderer.py) feeds BOTH the live overlay (box_item.py) and the bake (bake_typeset_page), so fixing breaks once fixes every committed render surface (D-01).

Output: New Qt-free `core/text_wrap.py` (tokenize_atoms + break_lines), wired into `layout()`'s manual and auto-fit paths with NoWrap documents, plus unit and regression tests.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/gui/text_renderer.py
@.planning/quick/260822-wvf-improve-auto-size-text-wrapping-smarter-/260822-wvf-RESEARCH.md

Key verified facts from RESEARCH.md (file read this session):
- `_build_document` (text_renderer.py:311–343) sets `setTextWidth(inner_w)` + `WrapAtWordBoundaryOrAnywhere` (line 325) — greedy, no balance/orphan control.
- `layout()` (lines 528–637): manual path calls `_build_document(text, style, size, inner_w)` once (line 568); auto-fit loop calls it per candidate size (line 590). Both paths are the integration points.
- `_style_font` int-rounds pixel size (line 278) — measurement must use the same rounded size.
- Vertical mode (`_vertical_placements` / `layout_vertical`) is per-char geometry — DO NOT TOUCH.
- Project lesson (STATE.md): Qt trims trailing whitespace at line ends; fit assertions are range-based ('word '×59 + 'word', 'hello world' @ 40pt cases).
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pure line breaker — tokenize_atoms() + break_lines() in core/text_wrap.py</name>
  <files>manga_ai_studio/core/text_wrap.py, tests/test_core/test_text_wrap.py</files>
  <behavior>
    - tokenize_atoms("I can't go") -> ["I", "can't", "go"] — apostrophes between two letters never split, variants `'` `’` `‘` `‛` `ʼ`; "rock 'n' roll" stays three atoms
    - Trailing punctuation glues to preceding atom: "Are you free ?" -> ["Are", "you", "free ?"] — glue set includes ? ! . , … : ; ' " ” ’ ) ] % AND fullwidth CJK ？！。，…（pitfall 6）
    - Leading open punctuation glues to following atom: "( [ { " “ « ¿ ¡" e.g. "(yes" is one atom
    - break_lines(["Are","you","free","?"], measurer, width) never places a line starting with "?" — punctuation rides its atom anyway, assert via atoms
    - DP balancing: given atoms where greedy yields a one-word last line but a balanced split exists (e.g. four equal-width words just fitting 2-per-line), break_lines returns no 1-atom last line (orphan penalty); same for 1-atom first line (widow penalty); a whole-text-single-word input still renders as that one line
    - Last-line raggedness is free (short last line not penalized vs mid lines)
    - Infeasible guard: an atom wider than `width` gets char-split by the tokenizer fallback so every emitted line fits (test: 10-char atom, width fits only 4 chars -> lines all <= width per measurer)
    - Empty/whitespace-only text -> [] lines
    - break_lines signature takes a Callable[[str], float] width measurer (Qt-free; headless-testable without pytest-qt)
  </behavior>
  <action>Create `manga_ai_studio/core/text_wrap.py` (Qt-free, stdlib+typing only):
  1. `tokenize_atoms(text: str) -> list[str]` — split on whitespace, then apply the gluing rules from RESEARCH §1: apostrophe-between-letters stays inside an atom (all five apostrophe variants); trailing-punctuation set glues leftward; leading-open-punctuation set glues rightward. Include an oversized-atom helper: `split_oversized(atom, max_chars)` or equivalent char-split applied later by break_lines when a single atom's measured width exceeds the available width (the WrapAtWordBoundaryOrAnywhere safety net replacement for CJK/no-space scripts).
  2. `break_lines(atoms_or_text, measure: Callable[[str], float], width: float, *, eps=1.0) -> list[str]` — accept either a raw string (tokenize first) or pre-tokenized atoms. O(n²) Knuth-Plass-lite DP per RESEARCH §2: best[j] = min over i<j of best[i] + cost(i,j); cost = raggedness² + demerits where raggedness = width − line_width (0 on the final line); infeasible (line_width > width + eps) = infinity; penalties: ORPHAN if last line has exactly 1 atom (n>1), WIDOW if first line has 1 atom, PER_LINE per extra line. eps defaults to ~1.0 px slack (pitfall 2 — outline ink extends beyond advance).
  3. Tunable module-level constants (ORPHAN_PENALTY, WIDOW_PENALTY, PER_LINE_COST) — plain floats, documented.
  Write tests FIRST in tests/test_core/test_text_wrap.py covering every behavior bullet above (pure pytest, no QApplication needed — pass a lambda measuring len(s)*char_w or similar deterministic measurer).</action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_wrap.py -q</automated>
  </verify>
  <done>All test_text_wrap.py cases pass; module imports with zero Qt imports (grep gate: no PySide6/QTextOption references in core/text_wrap.py); contractions, glued punctuation, orphan/widow balancing, and char-split fallback each locked by a named test.</done>
</task>

<task type="auto">
  <name>Task 2: Wire break_lines into layout() — both paths, NoWrap documents, regression tests</name>
  <files>manga_ai_studio/gui/text_renderer.py, tests/test_core/test_typeset_layout.py</files>
  <action>
  1. Add a `wrap: QTextOption.WrapMode = ...` keyword to `_build_document(text, style, size_px, inner_w, wrap=...)` defaulting to the current WrapAtWordBoundaryOrAnywhere so any other callers stay unchanged (verify callers with grep first — expected: only layout() plus possibly bake helpers).
  2. Add a private `_break_lines_for(text, style, size_px, inner_w) -> list[str]`: build `font = _style_font(style, size_px)` (SAME rounded pixelSize the doc gets — pitfall 1), `fm = QFontMetricsF(font)`, measurer = fm.horizontalAdvance (advance, NOT boundingRect), call `break_lines(text, measurer, inner_w)` from core/text_wrap. Import lazily or top-level as project convention dictates (check how text_renderer imports core modules).
  3. Manual path (line ~568): compute lines once, join with "\n", build document with `wrap=QTextOption.WrapMode.NoWrap`. overflow check unchanged (`doc.size().height() > inner_h + _EPS`) — honest overflow preserved.
  4. Auto-fit loop (line ~590): per candidate target size, recompute lines via `_break_lines_for(text, style, target, inner_w)` then `_build_document("\n".join(lines), style, target, inner_w, wrap=NoWrap)`. Fit check unchanged.
  5. Do NOT touch vertical mode, align_v/align_h handling, _line_rects, or the fit-loop constants — explicit-\n blocks flow through the existing rect/ink path untouched.
  6. Regression tests appended to tests/test_core/test_typeset_layout.py (follow that file's existing QApplication/qapp fixture pattern): for the three reported bad cases rendered through layout() into a wide-enough box — (a) "I can't believe it" produces no line ENDING in "can" / starting with "'t"; inspect doc.firstBlock().layout() line texts or LayoutResult.line_rects count + document toPlainText().split("\n"); (b) "don't stop" same contraction assertion; (c) "Are you free ?" produces no line STARTING with "?" (punctuation glued). Plus one balancing smoke: multi-word text in a box where greedy would orphan asserts the chosen lines differ from naive greedy OR simply that no line after the first is a single short atom when an alternative existed — keep it range/property-based per the platform-robust lesson (STATE.md line 237), never hard-coded pixel positions.</action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_typeset_layout.py tests/test_core/test_text_wrap.py -q</automated>
  </verify>
  <done>New regression tests fail against the old greedy behavior conceptually and PASS with the wired breaker; both manual and auto-fit paths emit NoWrap documents built from pre-broken \n lines; vertical-mode tests in test_typeset_layout.py unchanged and passing.</done>
</task>

<task type="auto">
  <name>Task 3: Full-suite regression pass</name>
  <files></files>
  <action>Run the complete suite with the pinned interpreter (AGENTS.md). Baseline before this task: 552 passed, 0 failed. If any existing fit/wrap tests shift (RESEARCH pitfall 4 — better breaks change line counts), re-derive their expectations from the NEW correct behavior and adjust assertions minimally, keeping them range-based; do NOT weaken unrelated assertions. Record the new baseline count.</action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>Full suite passes with 0 failures; suite count >= prior baseline (552) plus the new tests; any adjusted tests noted in the summary.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| translation text -> renderer | Arbitrary user/OCR/translation strings reach setPlainText |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QW-01 | Tampering | text_renderer._build_document | low | accept | Text still enters via doc.setPlainText (plain-text-only, ASVS V5 invariant preserved); break_lines operates on the same string, never builds rich text |
| T-QW-02 | Denial of Service | core/text_wrap.break_lines | low | mitigate | O(n²) DP over atoms — bubble text is tens of atoms; add a defensive cap (e.g. skip DP and fall back to single char-split pass if atom count exceeds a few thousand) |
</threat_model>

<verification>
- `pytest tests/test_core/test_text_wrap.py tests/test_core/test_typeset_layout.py -q` green (pinned interpreter)
- Full suite `pytest -q` green, >= 552 passed baseline + new tests
- `rg -c "PySide6" manga_ai_studio/core/text_wrap.py` == 0 (Qt-free breaker)
- `rg -n "WrapAtWordBoundaryOrAnywhere" manga_ai_studio/gui/text_renderer.py` shows it only as the _build_document default (or removed if no other caller needs it)
</verification>

<success_criteria>
- can't / don't render unbroken in both overlay and bake (shared layout() seam)
- No line begins with glued trailing punctuation (? ! , . … fullwidth variants)
- Orphan/widow one-word lines eliminated where a balanced alternative exists; oversized atoms still char-split within inner_w
- Vertical mode untouched; full suite green
</success_criteria>

<output>
Create `.planning/quick/260822-wvf-improve-auto-size-text-wrapping-smarter-/260822-wvf-SUMMARY.md` when done
</output>
