# Quick Research: Smarter auto-size text wrapping (orphan/fragment lines)

**Researched:** 2026-08-22
**Domain:** Line-breaking for the shared typeset renderer (`gui/text_renderer.py`)
**Confidence:** HIGH on codebase diagnosis (read this session); MEDIUM on algorithm details (textbook knowledge, not web-verified this session)

## Diagnosis — why the orphans happen [VERIFIED: manga_ai_studio/gui/text_renderer.py]

- Wrapping is entirely Qt's engine: `_build_document()` (lines 311–343) sets
  `doc.setTextWidth(inner_w)` and
  `opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)` (line 325).
  There is no balance or orphan control anywhere — Qt breaks greedily at word
  boundaries, and when a single word doesn't fit it falls back to
  break-anywhere, producing `can / 't`, `don' / t` fragments. Breaks before
  `?`/`!` occur when the source text has a space before the punctuation (the
  engine then sees a legitimate space break opportunity).
- Auto-fit (lines 570–607) only searches **font size**: grow ×1.1 while
  `candidate.size().height() <= inner_h` (cap `min(inner_w, inner_h)`), else
  shrink ×0.9, 12 iterations, 5 px floor at loop top. The *line breaks* at each
  size are whatever Qt's greedy engine produces. Smaller font → more room → but
  greedy still yields ragged, one-word lines when it barely fits.
- **The seam is perfect for a fix:** `layout()` is the single code path shared by
  the live overlay (`box_item.py:70` imports from `text_renderer`) and the bake
  (`bake_typeset_page` line 1031 calls the same `layout()` + `paint()`). Fix
  wrapping once inside `layout()` and both surfaces stay consistent (D-01).
- Vertical (tategaki) mode is per-char placements (lines 358–443) — **untouched**
  by this problem.

## Primary recommendation

**Compute line breaks ourselves (tokenizer + Knuth-Plass-lite DP), insert
explicit `\n`, render the document with `NoWrap`.** ~60–80 lines of pure,
headless-testable code in a new `manga_ai_studio/core/text_wrap.py` (Qt-free:
takes measured widths in, so it unit-tests without pytest-qt), consumed by
`_build_document`/`layout()`.

### Why not alternatives

| Option | Verdict |
|--------|---------|
| Vendor a Knuth-Plass PyPI package | Skip — no small, maintained package verified; ~60 lines is cheaper than a dependency risk. `[ASSUMED: package landscape]` |
| stdlib `textwrap` | Insufficient — greedy only, char-width based, no font metrics, no balance. `[ASSUMED]` |
| Keep engine wrap + post-fix rebalance by reading `lineAt()` text | Works but fights the engine; owning the breaks is cleaner and deterministic. |
| Only tune `WrapMode` | No Qt wrap mode does balancing or orphan control. `[ASSUMED: Qt docs]` |

## Implementation sketch

### 1. Tokenizer — "atoms" (fixes contractions + punctuation gluing)

Split on whitespace, then glue:

- **Contractions:** an apostrophe between two letter chars never splits —
  variants `'` `’` `‘` `‛` `ʼ`. `can't`, `don't`, `rock 'n' roll` stay whole.
- **Trailing punctuation** `? ! . , … : ; ' " ” ’ ) ] %` glues to the
  preceding atom (`free?` is one atom → never `free / ?`).
- **Leading open punctuation** `( [ { " “ « ¿ ¡` glues to the following atom.
- Optional secondary break opportunity **after** an interior hyphen
  (`long- / standing`) — low priority, off by default.
- **Oversized-atom fallback:** if one atom exceeds `inner_w` (long CJK run,
  URL), char-split it. This preserves today's
  `WrapAtWordBoundaryOrAnywhere` safety net for no-space scripts.

### 2. Knuth-Plass-lite DP (fixes orphans + balance)

For atoms `w[0..n)` with measured widths, `best[j] = min over i<j` of
`best[i] + cost(i, j)`:

- `cost = raggedness² + demerits`, where `raggedness = inner_w − line_width`
  (last line: raggedness 0 — a short last line is free).
- **Feasibility:** `line_width <= inner_w + eps`, else cost ∞ (with the
  oversized-atom fallback pre-applied, every line is feasible).
- **Penalties:** +`ORPHAN` if last line has exactly 1 atom (and n > 1);
  +`WIDOW` if first line has 1 atom; +`PER_LINE` per extra line (prefer fewer,
  larger lines — comic-lettering convention is few words per line, centered,
  but not one-word lines). `[ASSUMED: demerits formulation — textbook Knuth-Plass]`

O(n²) DP over atoms; bubble text is tens of atoms — negligible cost, and it
runs only ~a dozen times per fit loop.

### 3. Integration into `layout()` (the one seam)

```python
# inside the auto-fit loop, per candidate size:
font = _style_font(style, target)               # same rounded pixelSize the doc gets
fm = QFontMetricsF(font)
lines = break_lines(text, fm, inner_w)          # core/text_wrap.py — pure
candidate = _build_document("\n".join(lines), style, target, inner_w,
                            wrap=QTextOption.WrapMode.NoWrap)
```

- Apply in **both** the auto-fit and manual-size paths (manual sizes get
  better breaks too; `overflow` flag still reports honestly when the block
  exceeds `inner_h`).
- Use **`NoWrap`** on the document: our lines are pre-measured to fit; NoWrap
  guarantees Qt never second-guesses a break. Keep the existing
  `WrapAtWordBoundaryOrAnywhere` only if you want belt-and-braces (lines fit,
  so it should never trigger — but NoWrap makes the invariant explicit).
- `align_h` still works: Qt applies alignment to each explicit-`\n` line.
- Vertical mode: no changes.

## Pitfalls

1. **Measure with the exact render font.** `_style_font` int-rounds
   `setPixelSize` (line 278); measure with the same rounded size the document
   will use, or widths drift at the fit boundary. Use
   `QFontMetricsF.horizontalAdvance(line)` (advance, not `boundingRect` —
   bearing inflates bounds). `[VERIFIED: _style_font at text_renderer.py:273-279]`
2. **Outline/glow ink extends beyond advance.** Fit check is vertical-only
   (`doc.size().height()`), so this mostly doesn't matter, but add ~1 px slack
   to `inner_w` in the breaker to avoid hairline horizontal overflow.
3. **Trailing whitespace:** Qt trims it at line ends (recorded project lesson,
   STATE.md line 237) — the tokenizer splits on whitespace so lines never carry
   trailing spaces anyway.
4. **Existing fit tests may shift.** Tests were built as "platform-robust"
   against greedy wrap (STATE.md: 'word '×59 + 'word', 'hello world' at 40pt).
   Better breaks change line counts → run the full suite and re-derive
   expectations; assertions are range-based so most should survive.
5. **Inline editor scope boundary:** `inline_editor.py` is a live
   editing surface with its own Qt wrapping — out of scope; the fix targets the
   committed render (overlay + bake), which is where the complaint lives.
6. **CJK punctuation:** glue fullwidth `？！。，…` the same as ASCII — they
   arrive space-separated from some translations.

## How other tools do it `[ASSUMED — training knowledge, not verified this session]`

- **mokuro** renders HTML/CSS and lets the browser break lines — no orphan
  control either.
- **PanelCleaner** (vendored here) draws with PIL using simple greedy wrap —
  same class of problem.
- **BallonsTranslator** does custom rich-text layout with manual region
  fitting; closest prior art for "fit loop + own line breaking".
- **Comic lettering convention:** centered, 2–3 words/line max, never a
  one-word line unless the whole balloon is one word — exactly the DP
  penalties above.

## Suggested task split (for the planner)

1. `core/text_wrap.py`: `tokenize_atoms()` + `break_lines()` (pure, takes a
   `Callable[[str], float]` width measurer) + unit tests (contractions,
   punctuation gluing, orphan/widow, CJK char-split fallback).
2. Wire into `text_renderer.layout()` (both paths) with `NoWrap`; add
   `QFontMetricsF` measurement; regression tests via `layout()` on the
   reported bad cases ("can't", "don't", "Are you free ?").
3. Full-suite pass + visual UAT on real bubbles.

## Assumptions Log

| # | Claim | Risk if wrong |
|---|-------|---------------|
| A1 | No maintained tiny Python Knuth-Plass package worth vendoring | Low — hand-rolled is the recommendation regardless |
| A2 | Knuth-Plass demerits/orphan formulation as described | Low — textbook; penalties are tunable constants |
| A3 | Qt offers no wrap mode with balance/orphan control | Low — would only simplify the fix |
| A4 | Other tools' (mokuro/PanelCleaner/BallonsTranslator) wrapping behavior | Informational only |

All codebase claims are `[VERIFIED: manga_ai_studio/gui/text_renderer.py]` —
file read in full this session; line numbers cited inline.
