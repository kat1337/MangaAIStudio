---
status: passed
phase: 02-cleaning-output-batch
source: [02-VERIFICATION.md]
started: 2026-07-25T21:29:13Z
updated: 2026-07-26T01:23:41Z
---

# Phase 02 — Cleaning Output & Batch: User Acceptance Testing

## Context

All 4 plans are complete and committed. The automated verification passed **12/12 must-haves** (see `02-VERIFICATION.md`), and the full test suite is green (156 passed). The 02-04 blocking smoke-test's 6 manual checks were already user-approved after 2 fix cycles.

**One human item remains** — a deferred re-verification of `cleaned/` output quality that the user explicitly requested be tracked for later confirmation during the 02-04 smoke test. This UAT captures that single open check.

> 📌 This is the reminder the user asked for ("remind me of this later just to make sure") during the 02-04 checkpoint approval.

## Current Test

number: 1
name: Deliberate re-verification of `cleaned/` batch output quality
expected: |
  After running a Batch Detect+Clean (or Batch Clean after Batch Detect) on a
  real manga chapter folder (5+ pages) with real CTD + LaMa models loaded:

  1. OUTPUTS VISUALLY CLEAN — each file in `cleaned/` shows text removed and
     artwork restored (the LaMa inpainting ran, not a passthrough).
  2. NO-TEXT PAGES BYTE-IDENTICAL — pages where detection found no text (or
     where the user erased the mask to empty) must be byte-identical to their
     source file. This confirms the D-03 `shutil.copy2` passthrough is copying
     raw bytes + metadata, NOT silently re-encoding via PIL (which would change
     the bytes even for a visually-identical image).
       How to check: on Windows, `fc /b source\page.jpg cleaned\page.jpg`
       (or `certutil -hashfile ... MD5` on both and compare). Byte-identical
       means the hash/output is "no differences encountered".
  3. WRITE TARGET ISOLATION — files are written ONLY into the `cleaned/`
     subfolder. The source chapter folder must contain NO new/modified files
       (no cleaned outputs leaking into the source folder; T-02-01/T-02-02/
       T-02-03 write-target guards held).
result: pass
tested: 2026-07-26T01:23:41Z
notes: |
  User confirmed all three sub-checks passed on a real chapter with real CTD +
  LaMa models: outputs visually clean, no-text pages byte-identical (D-03 copy2
  passthrough confirmed not re-encoding), write-target isolation held (no files
  leaked into the source folder).

## Tests

### 1. Deliberate re-verification of `cleaned/` batch output quality

**Setup:**
- Project venv active (Phase 1 env, Python 3.12, numpy<2)
- Real CTD (~80MB) + LaMa (~200MB) model weights available (cached from Phase 1)
- A real manga chapter folder with 5+ pages, including at least one page with
  no detectable text (to exercise the passthrough path)

**Steps:**
1. Launch the app: `python -m manga_ai_studio`
2. `File → Open Folder` on the chapter
3. `File → Batch → Batch Detect + Clean`
4. Wait for completion (status bar: "Cleaned N/N pages")
5. Inspect the `cleaned/` subfolder next to the chapter

**Pass criteria (all three must hold):**
- [ ] **Visually clean** — open a few `cleaned/` pages; text is removed, artwork restored
- [ ] **Byte-identical passthrough** — for a no-text page, `fc /b source.jpg cleaned\source.jpg` reports no differences (or matching MD5 hashes)
- [ ] **Write-target isolation** — `git status`-equivalent check on the source folder shows no new/modified files outside `cleaned/`

expected: see above
result: pass

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

(none yet — to be filled if a check fails)
