---
id: ai-14
kind: subtask
status: to_do
created_at: '2026-05-17T10:57:41+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/codex_config.py
- src/ai_dotfiles/core/settings_merge.py
- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/remove.py
executor_agent: claude
---

# Codex target: settings.fragment to config.toml

## Goal

Translate a domain's `settings.fragment.json` into a project
`.codex/config.toml` — the keys that map (permissions, sandbox) land in
the TOML; hooks are skipped with an explicit message (ADR ai-1-5).

## Context files

- `src/ai_dotfiles/core/codex_config.py` — **new.** Read each installed
  domain's `settings.fragment.json`, translate the keys with a Codex
  equivalent (permissions, sandbox) into `.codex/config.toml`, and emit
  a fail-loud message for keys with no Codex equivalent (hooks). Use
  `tomli-w`; mark the file managed (`# managed-by` header) and use a
  `strip_owned` analogue so user-authored `config.toml` content
  survives. Reuse the merge/ownership shape from `settings_merge.py`.
- `src/ai_dotfiles/core/settings_merge.py` — read-only reference for the
  fragment-merge + ownership pattern.
- `src/ai_dotfiles/commands/install.py`, `remove.py` — for the Codex
  target, call `codex_config` to write / strip the managed config.

## Definition of done

- [ ] `codex_config.py` writes translatable `settings.fragment.json` keys (permissions, sandbox) into `.codex/config.toml`.
- [ ] Keys with no Codex equivalent (hooks) are skipped with an explicit fail-loud message in command output.
- [ ] The managed region is marker/header-delimited; `remove` strips only ai-dotfiles content, user `config.toml` text survives.
- [ ] Unit tests cover translation, the hooks skip, and ownership/strip.
- [ ] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- ADR ai-1-5 in epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md).
- ai-15 writes the `[mcp_servers]` section into the same file — keep the
  writer composable (do not assume sole ownership of `config.toml`).
