---
id: ai-3
kind: subtask
status: done
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/frontmatter.py
- src/ai_dotfiles/core/targets.py
- src/ai_dotfiles/core/paths.py
- src/ai_dotfiles/core/manifest.py
- src/ai_dotfiles/core/elements.py
- src/ai_dotfiles/core/dependencies.py
executor_agent: claude
---

# Codex target: core scaffolding

## Goal

Add the pure-`core/` foundation for multi-target support: a shared
frontmatter parser, a `Target` abstraction, Codex path resolvers, a
`get_targets()` manifest reader, and target-aware element resolution —
no command wiring, no filesystem rendering.

## Context files

- `src/ai_dotfiles/core/frontmatter.py` — **new.** Extract the YAML
  frontmatter parser currently duplicated inside `dependencies.py` into
  one function (`parse_frontmatter(text) -> dict`). Then make
  `dependencies.py` import it.
- `src/ai_dotfiles/core/targets.py` — **new.** `Target` enum
  (`CLAUDE`, `CODEX`) + per-`ElementType` render policy (where each
  element type goes and whether it is symlinked or rendered).
- `src/ai_dotfiles/core/paths.py` — add `project_codex_skills_dir(root)`
  → `<root>/.agents/skills`, `project_codex_agents_dir(root)` →
  `<root>/.codex/agents`. Path computation only, no I/O (module rule).
- `src/ai_dotfiles/core/manifest.py` — add `get_targets(path) -> list[str]`;
  absent `targets` field ⇒ `["claude"]` (ADR ai-1-3, backward compat).
- `src/ai_dotfiles/core/elements.py` — make `resolve_target_paths`
  target-aware (accept a `Target`, dispatch path/format per target).
- `src/ai_dotfiles/core/dependencies.py` — swap its inline frontmatter
  parsing for the new `frontmatter.py` (no behaviour change).

## Definition of done

- [x] `core/frontmatter.py` exists; `dependencies.py` uses it; no duplicated parser.
- [x] `core/targets.py` defines `Target` + render policy with type annotations.
- [x] `paths.py` exposes the two Codex path resolvers.
- [x] `manifest.get_targets()` returns `["claude"]` for a manifest with no `targets` key.
- [x] `resolve_target_paths` resolves Codex paths for `Target.CODEX`.
- [x] Unit tests added (`tests/unit/`) for `frontmatter`, `targets`, `get_targets`, Codex path resolution; `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- All design rationale is in epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md);
  do not restate it here.
- This subtask is foundation-only — ai-4 and ai-5 build on it. No
  `commands/` changes, no file writing.
