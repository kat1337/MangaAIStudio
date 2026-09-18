# MCP Agent Tools — Session Cache Issue

**Date:** 2026-07-12
**Affected agents:** all `gsd-*` agents declaring `mcp__*` wildcards in `tools:` (8 total — see table below)
**Status:** Fixed on disk for all 8 agents (both `~/.zcode/agents/` and `~/.claude/agents/`). Requires session restart to take effect. Backups in `.mcp-tools-backup-20260712-115916/` subdirs.

## Symptom

Spawning a GSD subagent fails with:

```
Required MCP server is not connected: context7, plugin_context7_context7, firecrawl, exa, tavily, ref, jina
```

…even after editing the agent's `tools:` frontmatter to remove the MCP wildcards.

## Root Cause

Two layers:

1. **ZCode keeps two copies of agent definitions.** The harness reads from `~/.zcode/agents/`, not `~/.claude/agents/`. Editing only the `.claude` copy has no effect.
   - `~/.claude/agents/gsd-ui-researcher.md` — Claude Code path (not used by ZCode)
   - `~/.zcode/agents/gsd-ui-researcher.md` — ZCode path (this is what the harness reads)

2. **Session-level caching.** ZCode loads agent definitions at session startup. Edits to the on-disk files are not picked up mid-session — the `Agent()` tool still uses the cached version with the original `tools:` list.

## Fix

Edit the `tools:` frontmatter line in **both** copies to remove the MCP server wildcards:

```diff
- tools: Read, Write, Edit, Bash, Grep, Glob, Skill, WebSearch, WebFetch, mcp__context7__*, mcp__plugin_context7_context7__*, mcp__firecrawl__*, mcp__exa__*, mcp__tavily__*, mcp__ref__*, mcp__jina__*
+ tools: Read, Write, Edit, Bash, Grep, Glob, Skill, WebSearch, WebFetch
```

Then **restart ZCode** (close and reopen the session).

## Which Agents Are Affected

Any agent with `mcp__*` wildcards in its `tools:` frontmatter and whose MCP servers are not connected. As of 2026-07-12 (second fix pass), these were the agents that **actually had** `mcp__*` on their `tools:` line (verified by grep, not by the prior table's blanket claim):

| Agent | Status | Note |
|-------|--------|------|
| `gsd-advisor-researcher` | fixed 2026-07-12 (2nd pass) | had context7 |
| `gsd-ai-researcher` | fixed 2026-07-12 (2nd pass) | had context7 |
| `gsd-domain-researcher` | fixed 2026-07-12 (2nd pass) | had context7 |
| `gsd-executor` | fixed 2026-07-12 (2nd pass) | had context7 |
| `gsd-phase-researcher` | fixed 2026-07-12 (2nd pass) | had context7 + firecrawl/exa/tavily/ref/jina/perplexity |
| `gsd-planner` | fixed 2026-07-12 (2nd pass) | had context7 — this was the one that blocked /gsd-plan-phase |
| `gsd-project-researcher` | fixed 2026-07-12 (2nd pass) | had context7 + firecrawl/exa/tavily/ref/jina/perplexity |
| `gsd-ui-researcher` | fixed 2026-07-12 (1st pass) | had context7 + firecrawl/exa/tavily/ref/jina |

The prior version of this table listed 16 agents as affected — that was the blanket list, not the verified set. `gsd-codebase-mapper`, `gsd-ui-auditor`, `gsd-debugger`, `gsd-doc-verifier`, `gsd-doc-writer`, `gsd-code-reviewer`, `gsd-code-fixer`, and `gsd-assumptions-analyzer` do **not** declare `mcp__*` on their `tools:` line (some mention MCP in body prose, which does not affect spawning).

**Check:** `grep -l "^tools:.*mcp__" ~/.zcode/agents/gsd-*.md` — note the `^tools:` anchor; a bare `grep -l "mcp__"` matches body prose too and over-reports.

## Quick Diagnostic

If a subagent spawn fails with `Required MCP server is not connected`:

1. Confirm which servers are actually configured: `grep -r "mcpServers" ~/.claude.json` — if empty, no MCP servers are wired up.
2. Find which agents reference MCP: `grep -l "mcp__" ~/.zcode/agents/gsd-*.md`
3. Strip the `mcp__*` wildcards from the `tools:` line in `~/.zcode/agents/<agent>.md` (keep WebSearch/WebFetch).
4. Restart ZCode.

## Recurrence Warning

**2026-08-27:** Found all 8 `~/.zcode/agents/` copies reverted to declaring `mcp__*` wildcards again (the `~/.claude/agents/` copies stayed clean) — almost certainly a GSD update reinstalling the stock frontmatter. A disk fix does not survive agent-definition reinstalls. If spawns start failing again after a GSD update, re-run the check below and re-strip:

```
grep -l "^tools:.*mcp__" ~/.zcode/agents/gsd-*.md
```

Second fix pass applied 2026-08-27 (backups: `.mcp-tools-backup-20260827-restartfix/`).

## Restoration

If MCP servers are later connected (Context7, Exa, Firecrawl, etc.), the wildcards can be restored to agent frontmatters. They are research fallbacks, not core requirements.
