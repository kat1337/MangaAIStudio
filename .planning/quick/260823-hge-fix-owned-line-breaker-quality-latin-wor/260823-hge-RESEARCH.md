# Quick Research: Owned line breaker quality — Latin word splits ("Herta!") & Japanese wrapping

**Researched:** 2026-08-23
**Domain:** Unicode line breaking (UAX #14), hyphenation, comic-typesetter prior art
**Confidence:** HIGH — every claim below verified against live sources this session (code files read; GitHub/PyPI/docs fetched)

## 1. Diagnosis: why "Herta!" became "Hert / a!"

**Ordering bug confirmed — it is exactly the suspected break-before-shrink interaction.**

- `_split_oversized` (`core/text_wrap.py:159-186`) **greedily char-splits ANY atom wider than `width + eps`** — including pure-Latin atoms like `"Herta!"`. It has no notion of script and no hyphenation.
- The auto-fit loop (`gui/text_renderer.py:642-672`) calls `_break_lines_for(text, style, target, inner_w)` at each candidate size **before** deciding whether that size fits, and its fit test is **vertical only** (`candidate.size().height() <= inner_h`, line 656). At an oversized candidate font, `"Herta!"` measures wider than `inner_w` → char-split into `"Hert"` + `"a!"` → those short lines now *fit vertically* → the loop accepts the candidate (`fit_held = True`) and grows/shrinks around a poisoned layout.
- The pre-owned Qt engine shrank the font first because `WrapAtWordBoundaryOrAnywhere` only broke anywhere as a *last resort inside* the engine's line builder. Our breaker made the emergency split unconditional and invisible to the fitter.

**Fix shape:** `break_lines()` must report *whether it had to break an unbreakable Latin atom*, and the auto-fit loop must treat that candidate as **not fitting** (keep shrinking); accept a split layout only at the 5 px floor / manual-size overflow. Char-splitting stays as the last-resort safety net — but only ever fires for CJK runs / URLs, never Latin words.

## 2. Candidate survey (all existence/license/API verified this session)

| Candidate | Status | License | Verdict |
|---|---|---|---|
| **uniseg 0.10.1** (PyPI, Jan 9 2026) `[VERIFIED: pypi.org/project/uniseg]` | Pure-Python UAX #14/#29; Unicode 16; **passes the entire Unicode line-break conformance suite** (since 0.9.0, Nov 2024) | MIT | **ADOPT** |
| **PyICU 2.16.2** `[VERIFIED: pypi.org/pypi/PyICU/json]` | ICU bindings — needs native ICU lib + compiler on Windows | ICU (BSD-style, GPL-compat) | Skip — build friction, redundant vs uniseg |
| **pyphen 0.18.1** (Kozea/CourtBouillon, Aug 14 2026) `[VERIFIED: pypi.org/project/pyphen]` | Pure-Python Hunspell hyphenation, LibreOffice dictionaries | GPL-2.0+/LGPL-2.1+/MPL-1.1 (GPLv3-compatible) | **ADOPT** |
| BallonsTranslator (dmMaze) `[VERIFIED: github.com/dmMaze/BallonsTranslator — 5.1k★, GPL-3.0]` | Renders via QTextDocument; Chinese sentence-split via pkuseg; no portable wrap algorithm | GPL-3.0 | Nothing to port |
| manga-image-translator (zyddnys) `[VERIFIED: github.com/zyddnys/manga-image-translator — 10.3k★, GPL-3.0]` | `merge_seg_eng` in `rendering/text_render_pillow_eng.py:10-31` is **plain greedy word wrap** (source fetched & read) | GPL-3.0 | Inferior to ours — nothing to port |
| mokuro (kha-white) `[VERIFIED: github.com/kha-white/mokuro — 1.7k★, GPL-3.0]` | HTML/CSS overlay; browser does wrapping | GPL-3.0 | Nothing to port |
| PanelCleaner (vendored `panelcleaner/`) | PIL `draw.text` greedy placement `[VERIFIED: panelcleaner/image_ops.py, structures.py:323]` | — | Nothing to port |

**Conclusion:** the open-source manga typesetters are all *behind* our K-P balancer. The right adoption is standards-grade **break opportunities** (uniseg) + real **hyphenation** (pyphen) fed into our existing DP — not porting anyone's renderer.

## 3. Recommended architecture (single path)

Keep `text_wrap.py`'s pipeline shape (atoms → oversized handling → DP/greedy → join). Change two stages:

```python
# Stage A — atoms: UAX #14 replaces whitespace splitting (fixes Japanese)
from uniseg import line_break_boundaries

def tokenize_atoms(text: str) -> list[str]:
    s = text.strip()
    return [s[a:b].strip() for a, b in zip(bnds, bnds[1:])]  # bnds = [0] + list(line_break_boundaries(s))
# uniseg units carry a trailing space — .strip() each; drop empties.
# Verified behavior [CITED: uniseg-py.readthedocs.io/linebreak]:
#   list(line_break_boundaries('あい、うえ、お。')) == [1, 3, 4, 6, 8]
#   → breaks between ideographs, NEVER before 、。 (kinsoku shori built in)
#   'Hello, world.' → one break after the space; "Herta!" stays whole.
# Keep the existing trailing/leading glue passes as belt-and-braces.

# Stage B — oversized atoms: pyphen before char-split (fixes "Herta!")
import pyphen
hyph = pyphen.Pyphen(lang="en_US")          # lang from the box's target language
# hyph.wrap("Herta!", width_chars) or better: hyph.iterate(word)
# → [(prefix, suffix), …] hyphenation points; take the longest prefix that
#   MEASURES <= width (QFontMetricsF), emit prefix + "-", recurse on suffix.
# Verified API [CITED: github.com/Kozea/Pyphen docs/common_use_cases.rst]:
#   dic.inserted('lettergrepen') == 'let-ter-gre-pen'; dic.iterate(...) yields split pairs.
# Raw char-split remains ONLY for atoms with no hyphenation points (CJK runs,
# URLs) — no dash appended there.
```

**Auto-fit ordering fix** (`gui/text_renderer.py:642-672`):
```python
lines, split_latin = break_lines_ex(text, fm.horizontalAdvance, inner_w)  # new return
fits = candidate.size().height() <= inner_h + _EPS and not split_latin  # ← reject
# at the 5 px floor / manual size: accept whatever we get (overflow honest)
```

### Answers to the two explicit questions
- **Char-split CJK-only?** Yes — after this change the raw char-split can only fire on scripts without spaces/hyphenation dictionaries (CJK, Hangul is fine via UAX#14 syllables, URLs). Latin words are never split; the font shrinks instead.
- **Hyphen appended?** Yes when breaking a Latin word at a Pyphen point: `"Herta-" / "la!"` style — measure the `-` and include it in the first segment's width. No dash for CJK/emergency char-splits.

## 4. Pitfalls

1. **uniseg units include the trailing space** — strip per unit or widths drift.
2. **Measure the appended `-`** with the same `horizontalAdvance`; don't assume glyph widths.
3. **Floor deadlock:** rejecting split candidates forever would bottom out at the 5 px floor with no layout — keep the existing "floor reached ⇒ accept" path so the split version is still emitted (with honest overflow).
4. **Atom explosion:** per-char CJK atoms raise atom counts; `MAX_ATOMS_FOR_DP` greedy fallback already covers this — leave it.
5. **Language source:** pick the Pyphen lang from the box's translation target language; fall back to `en_US` (use `pyphen.language_fallback`). Unknown lang raises — guard it.
6. **Vertical mode untouched** — per-char placements don't use the breaker.
7. **Existing tests** assert current split/glue outputs (`tests/test_core/test_text_wrap.py` etc.) — expect re-derived expectations for CJK inputs.

## 5. Package Legitimacy Audit

| Package | Registry | Age | Source Repo | Seam verdict | Disposition |
|---|---|---|---|---|---|
| uniseg | PyPI | since 2015 (0.10.1 Jan 2026) | bitbucket.org/emptypage/uniseg-py | SUS (unknown-downloads) | Approved — directly verified on PyPI (MIT, sig of life Jan 2026); seam lacks PyPI download stats. Planner: cheap human-verify glance at the Bitbucket repo is sufficient |
| pyphen | PyPI | since 2013 (0.18.1 Aug 2026) | github.com/Kozea/Pyphen | SUS (too-new, unknown-downloads) | Approved — Kozea/CourtBouillon (the WeasyPrint team), Trusted-Publishing + Sigstore attested release, verified on PyPI |
| PyICU | PyPI | long-lived | gitlab.pyicu.org | SUS (unknown-downloads) | Not adopted |

The SUS verdicts are artifacts of missing download-count data in the seam, not slopsquat signals — all three were fetched and read from authoritative sources this session. None have postinstall scripts.

## 6. Environment Availability

| Dependency | Required By | Available | Fallback |
|---|---|---|---|
| Python 3.14.2 (pinned) | both packages | ✓ | — |
| `uniseg` wheel (pure py3-none-any, 8.2 MB UCD data) | UAX #14 atoms | install needed: `pip install uniseg` | none needed |
| `pyphen` wheel (pure py3-none-any, supports 3.14) | Latin hyphenation | install needed: `pip install pyphen` | skip hyphenation, shrink-font-only |

No blocking dependencies. Both are pure-Python wheels — no compiler, consistent with the Qt-free/headless-testable constraint of `core/text_wrap.py`.

## Assumptions Log

| # | Claim | Risk if wrong |
|---|-------|---------------|
| A1 | uniseg perf is adequate for ~a dozen break calls × tens-of-units per bubble | Low — pure-Python but tiny inputs |
| A2 | Comic-lettering convention: hyphen on first segment when a word breaks | Cosmetic; tunable constant |

Everything else: verified/cited inline. Ready for planning.
