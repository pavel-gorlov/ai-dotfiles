---
id: ai-13
kind: task
status: wip
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
dependencies:
- ai-2
---

# Orchestrate Codex CLI target — Phase 3

## Context

Dispatch contract for Phase 3 of epic [ai-1](ai-1_openai-codex-cli-support-target-adapters.md)
— `config.toml` for the Codex target. Phase 1 (ai-2) shipped skills +
agents. Phase 3 maps domain `settings.fragment.json` and
`mcp.fragment.json` into a project `.codex/config.toml`. Independent of
Phase 2 (rules); depends only on Phase 1 (ai-2).

## What to do

Dispatch the three subtasks in dependency order.

- **Branch:** `feat/codex-config` — one branch, one PR for Phase 3.
- **PR title:** `feat: Codex CLI target — config.toml + MCP`.
- **Integration point:** ai-14 establishes the `config.toml` writer;
  ai-15 adds `[mcp_servers]` into the same file; ai-12... ai-16 documents.

### Dispatch order

```
ai-14  ─▶  ai-15  ─▶  ai-16
```

Strictly sequential — ai-15 writes into the `config.toml` file ai-14 owns.

## Subtask classification

| ID    | Title                                | Mode  | Context files (primary writes) |
|-------|--------------------------------------|-------|--------------------------------|
| ai-14 | Codex target: settings.fragment to config.toml | write | `core/codex_config.py`, `commands/{install,remove}.py` |
| ai-15 | Codex target: mcp.fragment to config.toml      | write | `core/codex_config.py` |
| ai-16 | Codex target: Phase 3 docs                     | write | `scaffold/templates/builtin_ai_dotfiles_skill.md`, `README.md` |

No read-only subtasks — all write, sequential per the Cognition rule.

## Acceptance criteria

- [ ] All three subtasks (ai-14…ai-16) are `done`.
- [ ] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green.
- [ ] A domain's `settings.fragment.json` translatable keys
      (permissions, sandbox) land in `.codex/config.toml`; hooks are
      skipped with an explicit logged message (ADR ai-1-5).
- [ ] A domain's `mcp.fragment.json` lands in the `[mcp_servers]`
      section of `.codex/config.toml`.
- [ ] PR `feat: Codex CLI target — config.toml + MCP` opened against `main`.

## Execution log

### ai-14 done (commit `f7646c5`)

Notes for ai-15 (MCP) — `.codex/config.toml` is a shared file:

- `core/codex_config.py` owns ONLY the top-level `[ai_dotfiles]` table
  (`MANAGED_TABLE`). ai-15 must write MCP under a DIFFERENT top-level
  table — `[mcp_servers]`. Never touch `ai_dotfiles`.
- Mirror the round-trip discipline: parse with `tomllib` → modify only
  your table → serialise with `tomli-w`. `render_config_toml(existing,
  managed)` already preserves any non-`ai_dotfiles` table.
- `write_codex_config` deletes the file only when no managed content
  AND no other tables remain — an MCP-only file survives a settings
  strip, and vice versa.
- Wire point: `install.py` `_install_codex_target` calls
  `_write_codex_config`; `remove.py` calls `_rebuild_codex_config`.
  ai-15 hooks in adjacently and must be idempotent.
- API: `write_codex_config(project_root, fragment_paths)`,
  `strip_managed(project_root)`, `config_path(project_root)`.

## Anti-patterns

- Starting before Phase 1 (ai-2 / PR #6) is merged.
- Trying to map `hooks` — Codex has no hook harness (ADR ai-1-5); skip
  with a message, do not fail.
