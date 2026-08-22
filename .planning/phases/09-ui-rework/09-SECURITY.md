---
phase: 9
slug: ui-rework
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-22
---

# Phase 9 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| filesystem→QIcon | Bundled SVG files read from disk and rendered by the Qt SVG plugin | Repo-bundled icon bytes (non-sensitive) |
| QSettings store→GUI | Persisted collapse-state strings read back and parsed at startup | Local view-state strings (non-sensitive; malformed values fail open to expanded) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-09a-01 | Tampering | `_icon()` loader (tools_strip.py) | low | mitigate | Icons resolve ONLY from `Path(__file__).parent / "assets" / "icons"` (module-relative, repo-bundled); no CWD/user-controlled path reaches QIcon; test asserts non-null QIcon + path containment | closed |
| T-09a-02 | Tampering | Strip tooltips (tools_strip.py) | low | accept | Plain-text copies of existing static action texts; no rich-text format introduced | closed |
| T-09b-01 | Tampering | sidePanel/*Expanded QSettings values (main_window.py `_read_side_panel_expanded`) | low | mitigate | Tolerant bool parse accepts only true/1/yes/on (case-insensitive); anything else — missing key or malformed/crafted value — falls back to EXPANDED; garbage cannot inject behavior beyond a section visibility flip | closed |
| T-09b-02 | Tampering | Section headers / chevron tooltips (side_panel.py) | low | accept | Plain-text labels with fixed contracted copy; no rich-text format introduced | closed |
| T-09c-01 | Tampering | Edit-section button labels/tooltips (side_panel.py EditSection) | low | accept | Labels/tooltips inherited verbatim from existing actions (plain text); no new user-input surface; dialog behavior unchanged | closed |
| T-09c-02 | Denial of Service | Menu slimming dropping keyboard access (main_window.py menus) | medium | mitigate | Shortcut audit encoded in tests: all existing tool/detect/inpaint shortcut tests pass unchanged (1018 passed, 0 failed at phase close); prohibition against any setShortcut removal enforced by test | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-09a-02 | T-09a-02 | Tooltips are plain-text copies of existing static action texts; no rich-text format is introduced | Planner disposition (plan 09-01), ratified by UAT test 3 | 2026-08-22 |
| AR-09b-02 | T-09b-02 | Section headers/chevron tooltips use plain-text fixed contracted copy; no rich-text format introduced | Planner disposition (plan 09-02), ratified by UAT test 3 | 2026-08-22 |
| AR-09c-01 | T-09c-01 | Edit-section labels/tooltips inherited verbatim from existing actions; no new input surface | Planner disposition (plan 09-03), ratified by UAT test 3 | 2026-08-22 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-22 | 6 | 6 | 0 | ox-alpha orchestrator (L1 grep verification: module-relative `_ICONS` path confirmed tools_strip.py:41; tolerant parse confirmed main_window.py:3134-3146 citing T-09b-01; shortcut audit suites green in full-suite run 1018 passed) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-22
