---
phase: 06
slug: refinement-polish-deferred-fixes-full-curve-editor
status: verified
threats_open: 0
asvs_level: 1
created: 2026-08-09
---

# Phase 6 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| curve widget mouse/key input → point state | Untrusted interaction (drag beyond bounds, double-clicks on endpoints, extreme nudge) crosses into point coordinates | point coordinates (bounded to [0,255]²) |
| dialog controls → preview_callback | Every control change drives the composed preview onto the canvas (display mutation only, no model writes) | composed preview ndarray |
| dialog exec result → undo stack | Apply path captures the undo before-state; a wrong capture (last preview frame) makes Ctrl+Z a no-op — undo-record integrity (V7 logic) | image before-state + undo record |
| menu/action surface → op dispatch | The renamed action must gate and dispatch identically to the Levels slot | action dispatch |
| canvas display paths → original/inpaint state | Capture-enabled vs capture-suppressed display paths gate the Show Original baseline and the inpaint-result claim | _original_image_numpy / _inpainted_qimage |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-01 | Tampering | curve_lut fancy-index/arange math | medium | mitigate | Backstop by construction: sort/dedupe/clip to [0,255] + np.interp + round().astype(np.uint8) — uint8 indices can never be out of range; verified image_ops.py:504-505; test_curve_lut_degenerate_backstop locks it | closed |
| T-06-02 | DoS | curves_page preview recompute | low | accept | Preview cost equals the existing levels_page cost (accepted since Phase 5); page size bounded by MAX_IMAGE_DIMENSION at load; histogram computed ONCE at open (D-08) | closed |
| T-06-03 | Tampering | _set_image_from_numpy empty-state visibility | low | mitigate | D-09 regression tests cover all three paths (project-open, numpy, preview); the call is idempotent with an image present | closed |
| T-06-04 | Tampering | QActionGroup exclusivity / set_active_tool sync | medium | mitigate | Exclusive group + checkable actions is the Qt contract; RED-gate tests cover shortcut/menu/programmatic paths; no toggled double-connects | closed |
| T-06-05 | Tampering | CurveWidget mouse/key handlers | medium | mitigate | All mutations clamp to [0,255]² with x-order preservation (curves_dialog.py clamp sites verified); endpoints y-locked (D-04); In spinbox range [prev_x+1, next_x-1]; curve_lut's T-05-07 backstop is the last line | closed |
| T-06-06 | DoS | histogram recompute / preview storm | medium | mitigate | Histogram computed ONCE at open (D-08); test_histogram_computed_once_at_open locks array identity; dialog never mutates models (Pitfall 9) | closed |
| T-06-07 | Tampering | _on_curves undo before-state capture | high | mitigate | b376f8a restore-before-Apply ordering preserved; test_curves_apply_pushes_one_entry asserts Ctrl+Z → byte-identical pre-dialog image + empty stack (ASVS V7) | closed |
| T-06-08 | Tampering | action/flash/undo-label rename sweep | low | mitigate | Grep gates for stale references + migrated flash assertions ("Curves applied.") + full-suite re-baseline (600 passed) | closed |
| T-06-09 | Tampering | _on_curves Cancel/apply-pre-restore baseline capture | high | mitigate | Both restores routed through the capture-suppressed preview path (main_window.py:1280, :1294, capture_original=False); no rebaseline on Cancel; test_curves_cancel_fresh_page_no_baseline_poison asserts _original_image_numpy stays None + has_inpaint_result False (ASVS V7) | closed |
| T-06-10 | Spoofing | _set_image_from_numpy _inpainted_qimage claim | high | mitigate | Gate `_inpainted_qimage` on capture_original (canvas.py:775); preview path cannot claim an inpaint result; capture-enabled callers keep the claim; test_inpaint_gui.py:256 contract re-verified | closed |
| T-06-11 | Tampering | _undo_op_label_for_result single-entry resolution | medium | mitigate | Prefer _last_geometry_op_name only for full-frame (0,0) image entries (history_manager.py:435 shape); bbox inpaint pops keep 'inpaint'; flash assertions + scoping guard test lock both directions (ASVS V7) | closed |
| T-06-12 | Tampering | set_active_tool sync / QActionGroup wiring | medium | mitigate | Window actions ungrouped (panel group = its 6 actions only); set_active_tool action-sync loop (blockSignals, main_window.py:3205-3216) + toolbar loop drive all surfaces; dock-click regression test (two consecutive clicks) + flipped membership assertions (ASVS V7) | closed |
| T-06-13 | Tampering | _make_tool_toolbar_button docstring | low | mitigate | Docstring rewritten to the actual mechanism; grep gates assert the stale group-membership claim is gone and the standalone mechanism is named | closed |
| T-06-SC | Tampering | pip installs | high | accept | N/A — zero new packages this phase (RESEARCH Package Legitimacy Audit: none) | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-02 | curves_page preview recompute cost equals the accepted Phase-5 levels_page cost; page size bounded at load | Developer (plan-time) | 2026-08-09 |
| AR-06-02 | T-06-SC | Zero new packages this phase — no supply-chain surface added | Developer (plan-time) | 2026-08-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-09 | 14 | 14 | 0 | gsd-security-auditor (L1 grep-depth, ASVS 1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-09
