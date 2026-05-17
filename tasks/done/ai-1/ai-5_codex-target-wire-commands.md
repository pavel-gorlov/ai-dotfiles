---
id: ai-5
kind: subtask
status: done
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/codex_install.py
- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/commands/remove.py
- src/ai_dotfiles/commands/status.py
dependencies:
- ai-4
executor_agent: claude
---

# Codex target: wire commands

## Goal

Make `install` / `add` / `remove` / `status` iterate the manifest's
`targets` and apply the Codex target to the filesystem — generated files
written, support files symlinked, drift detected.

## Context files

- `src/ai_dotfiles/core/codex_install.py` — **new.** The apply layer
  (business logic stays out of `commands/`):
  - install a skill — write generated `SKILL.md` (`render_skill_md`),
    symlink `scripts/` / `references/` / `assets/` into
    `.agents/skills/<name>/`;
  - install an agent — write rendered `.toml` (`render_agent_toml`) to
    `.codex/agents/<name>.toml`;
  - `is_stale(generated_path)` — compare `# source-sha256` header to the
    current source hash (ADR ai-1-1);
  - remove / prune managed files (identified by the `# managed-by` header).
- `src/ai_dotfiles/commands/{install,add,remove,status}.py` — iterate
  `get_targets()`; for `claude` keep current behaviour untouched; for
  `codex` call `codex_install`. `status` reports stale Codex agents.
  Drop `hooks` for the Codex target with an explicit logged skip.

## Definition of done

- [x] `core/codex_install.py` installs Codex skills (generated `SKILL.md` + symlinked support files) and agents (rendered `.toml`).
- [x] `install` / `add` / `remove` iterate `targets`; a Claude-only manifest behaves byte-identically to before.
- [x] `remove` and `install --prune` clean managed Codex files via the `# managed-by` header; user-authored files untouched.
- [x] `status` flags a Codex agent as stale when its `# source-sha256` no longer matches the source.
- [x] Hooks skipped for the Codex target with an explicit message in `install` output.
- [x] `pytest`, `mypy --strict`, `ruff`, `black` green (subtask-level tests; full coverage is ai-6).

## Notes

- `commands/` stays a thin wrapper — all logic in `core/codex_install.py`
  (project architecture rule).
- Depends on ai-4 (`codex_render`) and ai-3 (`targets`, `paths`, `get_targets`).
- ADRs in epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md).
