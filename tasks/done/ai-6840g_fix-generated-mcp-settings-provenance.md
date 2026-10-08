---
id: ai-6840g
kind: task
status: done
created_at: '2026-10-08T11:25:39+00:00'
parent: null
dependencies: []
status_history:
- at: '2026-10-08T11:25:39+00:00'
  status: to_do
- at: '2026-10-08T11:26:02+00:00'
  status: wip
  session:
    harness: codex
    id: 01a11b41-2fe7-7082-a764-9f71351dd9e1
- at: '2026-10-08T11:46:24+00:00'
  status: done
  session:
    harness: codex
    id: 01a11b41-2fe7-7082-a764-9f71351dd9e1
---

# Fix generated MCP settings provenance

## Context

After adding a catalog MCP domain in planch, `ai-dotfiles migrate` fails
with `LOCAL_ORIGINAL_UNPROVEN` for `enabledMcpjsonServers` in the generated
`.claude/settings.json`. Version 0.4.3 writes this field in `mcp_apply`, but
its settings ownership ledger only records permissions and hooks. The migration
therefore cannot distinguish a real generated contribution from local source.

## What to do

Record aggregate MCP settings provenance when the CLI actually writes its
contribution. Make DSH migration consume this provenance without claiming
arbitrary user aggregate settings. Preserve local originals, include backward
compatibility for existing ledgers, and verify install/add/reconcile/migrate
lifecycles. Update the shipped CLI skill and publish the bounded fix as 0.4.4
using the established GitHub wheel/sdist and Homebrew workflow.

## Acceptance criteria

- [x] CLI writes record real generated MCP settings ownership.
- [x] DSH migration accepts proven generated settings and blocks unproven local values.
- [x] Lifecycle regression tests and the repository quality gate pass.
- [x] Builtin skill and release notes explain the supported recovery workflow.

## Execution notes

- 2026-10-08: Created isolated worktree `/private/tmp/ai-dotfiles-dsh-mcp-provenance`
  on `fix/dsh-generated-mcp-provenance` from fresh `origin/main` at `e777c68`.
  Original source checkout and planch Git state are preserved.
- 2026-10-08: Record an optional `enabled_mcpjson_servers` proof in the existing
  settings ownership ledger: the actual injected names and exact-list hash.
  Preserve preexisting user overlaps and fail closed for edited/invalid proof.
  Retain proof-only ledgers across partial MCP removal failures so a retry
  cannot discard a user overlap. Legacy ambiguous overlaps remain unprovable.
- 2026-10-08: Independent final review found no remaining confirmed bugs.
  Final focused regression run: 44 passed, including 13 new lifecycle cases.
  Final full pytest: 2535 passed, 0 failed, 0 skipped, coverage 92.13%.
  Ruff, Black (186 files), mypy (87 source files), and Poetry metadata check
  passed. Evidence: `/private/tmp/dsh-mcp-provenance-release-20261008/`.
- 2026-10-08: Prepare version 0.4.4, matching documentation and shipped skill.
  Source PR/CI/merge, release assets and Homebrew publication follow the
  verified source commit; local source acceptance is complete.
