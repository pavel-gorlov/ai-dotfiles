---
id: ai-15
kind: subtask
status: done
created_at: '2026-05-17T10:57:41+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/codex_config.py
- src/ai_dotfiles/core/mcp_merge.py
- src/ai_dotfiles/core/mcp_apply.py
dependencies:
- ai-14
executor_agent: claude
---

# Codex target: mcp.fragment to config.toml

## Goal

Translate a domain's `mcp.fragment.json` into the `[mcp_servers]`
section of the project `.codex/config.toml`.

## Context files

- `src/ai_dotfiles/core/codex_config.py` — extend the writer from ai-14:
  read each installed domain's `mcp.fragment.json` and merge its servers
  into the `[mcp_servers]` table of `.codex/config.toml`. Keep the
  section managed/owned so `remove` strips ai-dotfiles servers and
  leaves user-defined ones.
- `src/ai_dotfiles/core/mcp_merge.py`, `mcp_apply.py` — read-only
  reference for how MCP fragments are merged + owned for the Claude
  target (`.mcp.json`); mirror that ownership discipline for TOML.

## Definition of done

- [x] A domain's `mcp.fragment.json` servers land in `[mcp_servers]` of `.codex/config.toml`.
- [x] `remove` strips ai-dotfiles-owned servers; user-defined `[mcp_servers]` entries survive.
- [x] The `config.toml` from ai-14 (settings) and ai-15 (MCP) coexist — neither overwrites the other's region.
- [x] Unit + integration tests cover merge, coexistence with ai-14 output, and ownership/strip.
- [x] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- Depends on ai-14 (the `codex_config.py` writer).
- ADR ai-1-5; epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md).
