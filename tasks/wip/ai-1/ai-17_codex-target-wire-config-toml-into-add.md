---
id: ai-17
kind: subtask
status: wip
created_at: '2026-05-17T13:32:13+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/core/codex_config.py
dependencies:
- ai-15
executor_agent: claude
---

# Codex target: wire config.toml into add

## Goal

Make `ai-dotfiles add @domain` write the added domain's
`settings.fragment.json` and `mcp.fragment.json` into `.codex/config.toml`
for the Codex target — closing the gap where only `install` did so.

## Context files

- `src/ai_dotfiles/commands/add.py` — the `add` command. ai-14/ai-15
  wired `.codex/config.toml` into `install` and `remove` only;
  `add` was left out. `add` already renders skills/agents/rules for the
  Codex target — extend it so it also invokes the `codex_config` writers
  (settings + MCP), consistent with `install`'s `_install_codex_target`.
- `src/ai_dotfiles/core/codex_config.py` — the writer (`write_codex_config`,
  `write_codex_mcp`); read-only here, just call it. Adding one domain
  must not drop other domains' managed regions — the writers already
  round-trip; pass the full installed-domain fragment set, not just the
  newly added one.

## Definition of done

- [ ] `ai-dotfiles add @domain` writes the domain's `settings.fragment.json`
      (translatable keys) and `mcp.fragment.json` into `.codex/config.toml`.
- [ ] The hooks-skipped message fires on `add` too (consistent with `install`).
- [ ] Adding a second domain does not drop the first domain's managed
      `config.toml` regions.
- [ ] Integration / e2e tests cover `add` writing `config.toml`.
- [ ] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- This subtask exists because ai-14/ai-15 were scoped to `install`/`remove`
  only; the gap surfaced during ai-15. Keep it surgical — `add` wiring,
  not a `codex_config` rewrite.
- `commands/` stays a thin wrapper — logic stays in `core/codex_config.py`.
