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

- [x] All four subtasks (ai-9…ai-12) are `done`.
- [x] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green
      (862 passed; mypy 56 files clean; ruff + black clean).
- [x] An always-on rule lands in the project-root `AGENTS.md`; a
      path-scoped rule lands in `<dir>/AGENTS.md`; a description-only
      rule renders as a Codex-only `rule-<name>` skill
      (covered by ai-11 integration + e2e tests).
- [x] `remove` strips only ai-dotfiles-owned `AGENTS.md` blocks; user
      text in `AGENTS.md` is untouched (covered by ai-11 tests).
- [ ] PR `feat: Codex CLI target — rules support` opened against `main`.

## Execution log

### ai-9 done (commit `4c13474`)

Notes for ai-10 / ai-11:

- `core/rule_classify.py`: `classify_rule(md_path) -> RuleClass`;
  `RuleClass` ∈ `ALWAYS_ON` / `PATH_SCOPED` / `DESCRIPTION_ONLY`.
  Priority: non-empty `paths:` → `PATH_SCOPED` (wins over `always_on`);
  else `always_on: true` → `ALWAYS_ON`; else `DESCRIPTION_ONLY`.
- New `RenderMode.DISPATCH`: `RENDER_POLICY[CODEX][RULE]` is now
  `DISPATCH` — the signal that the command layer must `classify_rule`
  and route by `RuleClass` (it does not auto-route).
- `elements.py` `resolve_target_paths` / `_codex_pair_for` **still
  hard-raises `ElementError` for `rule:` + `CODEX`** — ai-11 must relax
  this and wire the real routing.
- `core/codex_targets.py` `iter_codex_pairs` currently returns no pairs
  for standalone rules (placeholder bail). ai-11 replaces it; the test
  `test_codex_targets.py::test_standalone_rule_yields_no_pairs` will
  then need updating.

### ai-10 done (commit `2807b1b`)

Notes for ai-11 (wiring `agents_md.py` into commands):

- API: `rule_block_targets(md_path, project_root, rule_class_value)`
  returns the `AGENTS.md` paths to write; `upsert_rule_block(agents_md,
  name, body)` writes one block (idempotent, returns `False` on no-op);
  `strip_rule_blocks(text, {name})` removes owned blocks; `rule_name_of`
  derives the block / `rule-<name>` name.
- `rule_class` is passed as the `RuleClass.value` **string** (avoids an
  import cycle). `DESCRIPTION_ONLY` is rejected by `rule_block_targets`
  with `ElementError` — ai-11 routes those to the Codex-only skill path
  *before* calling `agents_md`.
- `upsert_rule_block` wants the **frontmatter-stripped body** — extract
  it the way `codex_render._split_body` does (consider exposing a shared
  helper).
- Ownership is self-describing via the in-file markers — **no separate
  ownership JSON** is needed (unlike `settings_ownership.py`).
- An `AGENTS.md` left whitespace-only after a strip is a deletion
  candidate — ai-11 decides; `agents_md.py` never deletes files.

### ai-11 done (commit `1450d4f`)

Shipped behaviour for ai-12 (docs):

- `targets: ["codex"]` now renders rules. A `rule:` / domain `rules/`
  member dispatches by `RuleClass`: `always_on: true` → managed block in
  `<project>/AGENTS.md`; non-empty `paths:` → managed block in
  `<dir>/AGENTS.md` per path (glob `src/**` → `src/`); neither (the
  un-migrated default) → synthetic Codex-only skill `rule-<name>` under
  `.agents/skills/`.
- Synthetic `rule-<name>` skills are Codex-only (ADR ai-1-2); the rule
  still symlinks into `.claude/rules/` for the Claude target.
- `AGENTS.md` ownership is self-describing via
  `<!-- ai-dotfiles:rule:<name> START/END -->` markers; `remove` strips
  only those and deletes an `AGENTS.md` left whitespace-only.
- `install --prune` strips orphaned `AGENTS.md` blocks + synthetic
  skills. `status` reports `rules/<name>` and `skills/rule-<name>`.
- New public API to mention: `codex_render.render_rule_skill_md`,
  `codex_render.split_body`. Rule frontmatter (`always_on:` / `paths:`)
  is the migration knob — a rule-authoring note should cover it.

## Anti-patterns

- Starting before Phase 1 (ai-2 / PR #6) is merged — Phase 2 builds on
  the Codex target infra from Phase 1.
- Treating description-only rules as `AGENTS.md` content — ADR ai-1-2
  renders them as Codex-only skills.
