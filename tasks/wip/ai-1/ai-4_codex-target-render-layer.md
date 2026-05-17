---
id: ai-4
kind: subtask
status: to_do
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/codex_render.py
- src/ai_dotfiles/core/frontmatter.py
- src/ai_dotfiles/core/targets.py
- pyproject.toml
dependencies:
- ai-3
executor_agent: claude
---

# Codex target: render layer

## Goal

Pure string transforms that turn a catalog element into its Codex
on-disk form: a catalog agent `.md` → Codex `.toml`, and a catalog
`SKILL.md` → a Codex `SKILL.md` with a trimmed description.

## Context files

- `src/ai_dotfiles/core/codex_render.py` — **new.** Two functions:
  - `render_agent_toml(md_path) -> str` — parse frontmatter
    (`core/frontmatter.py` from ai-3) → TOML keys `name`, `description`,
    `developer_instructions` (the MD body), plus optional `model`.
    Use `tomli-w` for serialisation.
  - `render_skill_md(md_path) -> str` — re-emit `SKILL.md` with the
    `description` trimmed to its first sentence, trigger phrases dropped
    (ADR ai-1-4).
  - Both prepend a header: `# managed-by: ai-dotfiles` and
    `# source-sha256: <hash of source file content>` (ADR ai-1-1).
    `tomli-w` emits no comments — prepend the header as raw text.
- `src/ai_dotfiles/core/frontmatter.py` — consumed (from ai-3), read-only.
- `src/ai_dotfiles/core/targets.py` — consumed (from ai-3), read-only.
- `pyproject.toml` — add the `tomli-w` dependency; refresh `poetry.lock`.

## Definition of done

- [ ] `render_agent_toml` produces valid TOML (`name`, `description`, `developer_instructions`, optional `model`) with the managed-by + source-sha256 header.
- [ ] `render_skill_md` trims `description` to the first sentence and carries the same header.
- [ ] `tomli-w` added to `pyproject.toml`; `poetry.lock` regenerated.
- [ ] String escaping is correct for multi-line bodies and bodies containing quotes / backticks.
- [ ] Unit tests (`tests/unit/test_codex_render.py`) cover agent + skill render, header presence, hash stability; `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- Render functions are **pure** — they take a path, return a string. No
  writing, no symlinks, no command logic; that is ai-5.
- Depends on ai-3 for `core/frontmatter.py` and `core/targets.py`.
- ADR ai-1-1 / ai-1-4 in epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md).
