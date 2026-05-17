---
id: ai-2
kind: task
status: wip
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
dependencies: []
---

# Orchestrate Codex CLI target — Phase 1

## Context

Dispatch contract for Phase 1 of epic [ai-1](ai-1_openai-codex-cli-support-target-adapters.md)
— the MVP: a `targets` manifest field plus skill + agent rendering for
the Codex CLI target, project-scoped. Phases 2–3 are broken down
separately after this PR merges.

All design decisions live in the epic (ADR ai-1-1…ai-1-5) — subtasks
reference them, never restate them.

## What to do

Dispatch the five subtasks below in dependency order. This task is not
itself executable work; it is the wiring.

- **Branch:** `feat/codex-target` — one branch, one PR for all of Phase 1.
- **PR title:** `feat: Codex CLI target support (skills + agents)`.
- **Integration point:** after ai-5, the CLI is functional end-to-end;
  ai-6 (tests) and ai-7 (docs) validate and document it.

### Dispatch order

```
ai-3  ─▶  ai-4  ─▶  ai-5  ─▶  ┬─▶ ai-6
                              └─▶ ai-7
```

ai-3 → ai-4 → ai-5 are strictly sequential (shared core files). ai-6 and
ai-7 both depend on ai-5; their `context_files` do not overlap
(`tests/` vs docs files), so they *may* run in parallel — but
single-threaded is the default; parallelise only if needed.

## Subtask classification

| ID   | Title                        | Mode  | Context files (primary writes) |
|------|------------------------------|-------|--------------------------------|
| ai-3 | Codex target: core scaffolding | write | `core/frontmatter.py`, `core/targets.py`, `core/paths.py`, `core/manifest.py`, `core/elements.py`, `core/dependencies.py` |
| ai-4 | Codex target: render layer   | write | `core/codex_render.py`, `pyproject.toml` |
| ai-5 | Codex target: wire commands  | write | `core/codex_install.py`, `commands/{install,add,remove,status}.py` |
| ai-6 | Codex target: Phase 1 tests  | write | `tests/integration/`, `tests/e2e/` |
| ai-7 | Codex target: Phase 1 docs   | write | `scaffold/templates/builtin_ai_dotfiles_skill.md`, `README.md`, `CLAUDE.md` |

No read-only subtasks — no fan-out. Every subtask mutates files; run
sequentially per the Cognition rule. ai-3→ai-4→ai-5 have overlapping
core-module surface and **must** be sequential.

## Acceptance criteria

- [ ] All five subtasks (ai-3…ai-7) are `done` with their own acceptance met.
- [ ] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green.
- [ ] A scratch project with `"targets": ["codex"]` produces working
      `.agents/skills/` and `.codex/agents/*.toml` after `ai-dotfiles install`.
- [ ] A manifest without `targets` installs byte-identically to pre-change behaviour.
- [ ] PR `feat: Codex CLI target support (skills + agents)` opened against `main`.

## Anti-patterns

- Dispatching ai-4 before ai-3 is `done` — the render layer imports the
  `Target` enum and the extracted frontmatter parser from ai-3.
- Letting a subtask touch files outside its `context_files` — surfaces
  as a merge conflict with the next sequential subtask.
- Restating epic ADRs inside subtask bodies — reference `ai-1` instead.
