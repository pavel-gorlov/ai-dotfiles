---
id: ai-8
kind: task
status: wip
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
dependencies:
- ai-2
---

# Orchestrate Codex CLI target — Phase 2

## Context

Dispatch contract for Phase 2 of epic [ai-1](ai-1_openai-codex-cli-support-target-adapters.md)
— rules for the Codex target. Phase 1 (ai-2) shipped skills + agents;
Phase 2 adds rule rendering. Depends on Phase 1 being merged (ai-2).

Rules classify three ways (epic ADR ai-1-2):
- **always-on** → managed block in the project-root `AGENTS.md`.
- **path-scoped** (new rule frontmatter field `paths:`) → managed block
  in `<dir>/AGENTS.md`, activated by Codex's root→cwd walk.
- **description-only** → synthetic Codex-only skill named `rule-<name>`.

## What to do

Dispatch the four subtasks in dependency order. Not executable work
itself — the wiring.

- **Branch:** `feat/codex-rules` — one branch, one PR for Phase 2.
- **PR title:** `feat: Codex CLI target — rules support`.
- **Integration point:** after ai-11 the CLI renders rules end-to-end;
  ai-12 documents it.

### Dispatch order

```
ai-9  ─▶  ai-10  ─▶  ai-11  ─▶  ai-12
```

Strictly sequential — shared core surface.

## Subtask classification

| ID    | Title                          | Mode  | Context files (primary writes) |
|-------|--------------------------------|-------|--------------------------------|
| ai-9  | Codex target: rule classification | write | `core/rule_classify.py`, `core/targets.py` |
| ai-10 | Codex target: AGENTS.md assembly  | write | `core/agents_md.py` |
| ai-11 | Codex target: wire rules          | write | `core/codex_install.py`, `core/codex_targets.py`, `commands/{install,remove,status}.py` |
| ai-12 | Codex target: Phase 2 docs        | write | `scaffold/templates/builtin_ai_dotfiles_skill.md`, `README.md` |

No read-only subtasks — all write, sequential per the Cognition rule.

## Acceptance criteria

- [ ] All four subtasks (ai-9…ai-12) are `done`.
- [ ] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green.
- [ ] An always-on rule lands in the project-root `AGENTS.md`; a
      path-scoped rule lands in `<dir>/AGENTS.md`; a description-only
      rule renders as a Codex-only `rule-<name>` skill.
- [ ] `remove` strips only ai-dotfiles-owned `AGENTS.md` blocks; user
      text in `AGENTS.md` is untouched.
- [ ] PR `feat: Codex CLI target — rules support` opened against `main`.

## Anti-patterns

- Starting before Phase 1 (ai-2 / PR #6) is merged — Phase 2 builds on
  the Codex target infra from Phase 1.
- Treating description-only rules as `AGENTS.md` content — ADR ai-1-2
  renders them as Codex-only skills.
