---
phase: quick-260823-hge
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - manga_ai_studio/core/text_wrap.py
  - manga_ai_studio/gui/text_renderer.py
  - tests/test_core/test_text_wrap.py
autonomous: true

estimate:
  tokens: 58000
  raw_tokens: 32000
  tasks: 2
  confidence: med

must_haves:
  truths:
    - A Latin word wider than the box (e.g. "Herta!") is never char-split mid-word without a hyphenation dash — it either hyphenates at a dictionary point ("Hert-" / "a!") or the layout shrinks the font before accepting a split.
    - The auto-fit loop REJECTS any candidate whose layout required breaking a Latin word, and keeps shrinking down to the 5 px floor before ever emitting a split layout.
    - Japanese text wraps at UAX #14 boundaries — between ideographs, never before 、。？！ (kinsoku shori), punctuation still glued so no line starts with closing punctuation.
    - Raw char-split fires ONLY for atoms with no hyphenation points (CJK runs, URLs); Latin words get pyphen hyphenation with "-" measured as part of line width.
    - Missing uniseg/pyphen degrades gracefully (whitespace tokens / shrink-font-only), never crashes.
  artifacts:
    - pyproject.toml lists uniseg + pyphen (single source of truth, commented)
    - manga_ai_studio/core/text_wrap.py — uniseg-based tokenize_atoms + pyphen-hyphenating _split_oversized + break_lines_ex() -> (lines, split_latin)
    - manga_ai_studio/gui/text_renderer.py — _break_lines_for returns the split flag; auto-fit loop consumes it
    - tests/test_core/test_text_wrap.py — Herta!/CJK/fallback/exemption coverage green
  key_links:
    - break_lines_ex split_latin flag -> layout() fit predicate (the ordering-bug kill link)
    - pyphen hyphenation points -> measurer-consistent widths (dash included in prefix measurement)
    - uniseg line_break_boundaries -> existing glue passes (idempotent composition)
---

<objective>
Fix owned line-breaker quality: Latin words must never char-split mid-word without a hyphenation dash ("Herta!" rendered as "Hert/a!"), Japanese/CJK wrapping becomes standards-grade, by adopting uniseg (UAX #14) + pyphen and fixing the break-before-shrink ordering bug in the auto-fit loop.

Purpose: The current breaker greedily char-splits ANY oversized atom — including pure-Latin words — and the auto-fit loop accepts those poisoned layouts because its fit test is vertical-only. Real comic typesetting needs hyphenated Latin breaks and kinsoku-respecting CJK wraps.

Output: Updated core breaker + renderer fit loop + green test suite (pinned interpreter).
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/quick/260823-hge-fix-owned-line-breaker-quality-latin-wor/260823-hge-RESEARCH.md
@manga_ai_studio/core/text_wrap.py
@manga_ai_studio/gui/text_renderer.py (lines 381-394 `_break_lines_for`, lines 608-701 horizontal layout/auto-fit)
@tests/test_core/test_text_wrap.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Standards-grade core breaker — uniseg atoms + pyphen hyphenation + split_latin signal</name>
  <files>pyproject.toml, manga_ai_studio/core/text_wrap.py, tests/test_core/test_text_wrap.py</files>
  <behavior>
    - tokenize_atoms("Hello, world.") -> ["Hello,", "world."] (one UAX #14 break after the space; "Herta!" stays ONE atom)
    - tokenize_atoms("あい、うえ、お。") -> ["あい、", "うえ、", "お。"]-grade units (stripped): breaks between ideographs/clauses, NEVER producing an atom starting with 、 or 。
    - Glue passes compose: "Are you free ?" still yields the glued "free ?" atom (glue runs AFTER uniseg tokenization, idempotent)
    - Oversized Latin atom "Herta!" at a width fitting only "Hert-" hyphenates: emits "Hert-" + "a!" (or equivalent longest-prefix split), dash measured as part of the first segment's width via the SAME measure callable; split_latin=True
    - Oversized Latin atom with NO pyphen hyphenation points falls back to char-split (last resort), split_latin=True, no dash
    - Short ALL-CAPS Latin word (define module constant, e.g. _ALL_CAPS_NO_HYPHEN_MAX_LEN = 6) skips hyphenation — goes to char-split last resort (comic convention, agent discretion on the exact bound)
    - Oversized CJK atom (no hyphenation dictionary applies): char-split exactly as today, split_latin=False (CJK splits are legitimate wrapping, not a poison signal)
    - break_lines_ex(text_or_atoms, measure, width, eps=..., lang="en_US") -> (lines, split_latin); break_lines() remains a thin wrapper returning lines only — every existing call site/test keeps working
    - Fallbacks: uniseg missing -> tokenize_atoms falls back to .split(); pyphen missing or unknown lang (guard with pyphen.language_fallback try/except) -> hyphenation skipped, char-split remains the safety net; module NEVER raises ImportError at import time (lazy imports inside functions, mirroring the project's manga-ocr lazy-import pattern)
    - Zero Qt references in text_wrap.py (existing headless gate test stays green)
    - RED-first: write the failing Herta! hyphenation test + the CJK boundary test before implementing
  </behavior>
  <action>
    First install the two packages into the PINNED interpreter AND declare them in pyproject.toml dependencies (single source of truth per the file's own comment convention — add with a brief comment citing this quick task):
      & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pip install uniseg pyphen
    (Both are pure-Python wheels, verified on PyPI this session per RESEARCH §5/§6 — MIT and GPL-compatible respectively.)

    In core/text_wrap.py:
    1. Rewrite tokenize_atoms to derive units from uniseg.line_break_boundaries (RESEARCH §3 Stage A): build boundary list, slice, .strip() EACH unit (uniseg units carry a trailing space — pitfall 1), drop empties. Then run the EXISTING _absorb_leading + _glue_trailing passes on top unchanged (they are idempotent and keep "free ?"-style author-space gluing working). On ImportError, fall back to the current text.split(). This replaces whitespace-only tokenization and fixes Japanese wrapping while preserving contractions (uniseg never splits inside "can't").
    2. Rewrite _split_oversized (Stage B): classify each oversized atom. A LATIN atom (contains ASCII letters, no CJK ideographs — simple script scan) first tries pyphen: lazily build a cached pyphen.Pyphen(lang) via a module-level factory guarded by language_fallback try/except returning None on failure; use dic.iterate(atom) hyphenation points, take the LONGEST prefix whose measured width (prefix + "-", measured with the same measure callable — pitfall 2: never assume glyph widths) fits width+eps, emit prefix+"-", recurse on the suffix. Skip hyphenation for short all-caps words (module constant, comic convention). Non-Latin or hyphenation-unavailable atoms keep the existing greedy per-char fill verbatim (CJK runs, URLs) — no dash appended there.
    3. Thread a split signal: internal helpers track whether any LATIN word was broken (hyphenated or char-split). New public break_lines_ex(..., lang="en_US") returns (lines, split_latin: bool); break_lines becomes a wrapper discarding the flag. CJK char-splits do NOT set the flag (they are correct wrapping, not a fit failure).
    4. Update the module docstring's atom-rules section to describe UAX #14 + hyphenation (keep the zero-Qt guarantee).

    Tests in tests/test_core/test_text_wrap.py: keep every existing test green except re-derive CJK-input expectations per pitfall 7 (whitespace-split CJK strings now tokenize differently); add the behaviors above using fake measure callables (monospace-style lambda) so tests stay Qt-free and deterministic. Include a fallback test that forces the lazy-import miss (monkeypatch the import seam or sys.modules) asserting graceful degradation, and an all-caps exemption test.

    Package legitimacy: both packages were verified on PyPI from authoritative sources this session (RESEARCH §5 — uniseg MIT since 2015, pyphen Kozea/CourtBouillon with Sigstore-attested releases); no blocking checkpoint required.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_wrap.py -x -q</automated>
  </verify>
  <done>All breaker unit tests pass under the pinned interpreter including new Herta!-hyphenation, CJK-boundary, all-caps-exemption, and fallback-degradation cases; break_lines back-compat intact; pyproject declares uniseg + pyphen.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Auto-fit ordering fix — reject Latin-split candidates before shrinking to floor</name>
  <files>manga_ai_studio/gui/text_renderer.py, tests/test_core/test_typeset_layout.py</files>
  <behavior>
    - Auto-fit candidate whose break produced split_latin=True is treated as NOT fitting (even when its height fits) — the loop shrinks further (RESEARCH §3 ordering fix)
    - At the 5 px floor the loop accepts whatever it gets (floor deadlock escape, RESEARCH pitfall 3) — the split layout IS emitted with honest overflow rather than no layout at all
    - A narrow box containing "Herta!" ends at a smaller accepted font with "Herta!" whole (hyphenated or unsplit), never "Hert"/"a!" at a larger size
    - Manual-size path keeps today's semantics: owned breaks at the chosen size, vertical-only overflow honesty (author intent wins)
    - Vertical/tategaki layout untouched (per-char placements never call the breaker)
  </behavior>
  <action>
    In gui/text_renderer.py:
    1. Change _break_lines_for to return the tuple from core break_lines_ex (lines, split_latin) — rename or wrap so BOTH call sites (manual path line ~617, auto-fit loop line ~648) unpack it.
    2. In the auto-fit loop, extend the fit predicate: candidate accepted only when candidate.size().height() <= inner_h + _EPS AND NOT split_latin. On rejection with fit_held False, continue the existing shrink path; the floor check at the loop TOP stays the escape hatch (accept the final candidate, overflow honest). Do not touch grow-phase logic beyond the predicate.
    3. Manual path: ignore the flag (unchanged overflow contract) but still render the hyphenated lines break_lines_ex produces.
    4. Update the docstring/comments at both sites to state the ordering rule: a layout that had to break a Latin word is a failed fit, not a result.

    Regression tests (tests/test_core/test_typeset_layout.py follows its existing platform-robust range-based assertion discipline — see the accumulated decisions on Test A/Test E glyph-metric variance):
    - Narrow-box "Herta!" auto-fit test asserting the accepted used_font_size_px is strictly smaller than the base target AND the emitted lines contain no mid-word split lacking a hyphen dash
    - Floor-escape test: text forcing split even at floor still yields a LayoutResult (overflow True), not an exception or empty document
    - Manual-size smoke: hyphenated lines render and overflow stays vertically computed

    NOTE: layout()-level tests require QApplication (pytest-qt, as existing typeset_layout tests do).
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_wrap.py tests/test_core/test_typeset_layout.py -q && & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>Full suite green under the pinned interpreter (baseline 552 passed or better — strict superset with the new tests); "Herta!" can no longer be accepted as a split layout above the floor; CJK wrapping respects kinsoku via UAX #14.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| PyPI -> pinned venv | Two new third-party packages enter the runtime (uniseg, pyphen) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QH-01 | Tampering (supply chain) | uniseg 0.10.1 / pyphen 0.18.1 installs | medium | mitigate | Verified on PyPI from authoritative sources this session (RESEARCH §5: uniseg MIT since 2015; pyphen Kozea/CourtBouillon, Sigstore-attested Trusted Publishing); pure-Python wheels, no postinstall scripts; declared in pyproject as single source of truth |
| T-QH-02 | Denial of Service | pyphen.iterate on pathological long tokens | low | accept | Inputs are bubble-scale text (tens of atoms); MAX_ATOMS_FOR_DP greedy cap already bounds pathological inputs |
| T-QH-03 | Denial of Service | uniseg boundary scan on huge inputs | low | accept | Same bubble-scale input profile (RESEARCH assumption A1); fallback path exists |
</threat_model>

<verification>
- Pinned interpreter runs: text_wrap unit tests, typeset_layout regression tests, then the FULL suite — all green
- grep confirms text_wrap.py still contains zero Qt references (existing headless gate test enforces this)
- pyproject.toml carries uniseg + pyphen in [project] dependencies
</verification>

<success_criteria>
- Latin words never char-split mid-word without a hyphenation dash above the 5 px floor
- Auto-fit prefers a smaller unsplit font over a larger split one; floor still yields an honest overflow layout
- Japanese text wraps at UAX #14 opportunities with kinsoku respected (no line starts with 、。？！)
- Graceful degradation when uniseg/pyphen are absent — no import-time crash anywhere
- Full suite passes under C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe
</success_criteria>

<output>
Create `.planning/quick/260823-hge-fix-owned-line-breaker-quality-latin-wor/260823-hge-SUMMARY.md` when done
</output>
