---
id: ai-18
kind: task
status: done
created_at: '2026-05-17T17:39:40+00:00'
parent: ai-1
dependencies: []
---

# Fix: path-scoped rules with file-glob paths create literal-glob dirs

## Context

Bug found in real-world use of Phase 2 (rules → Codex, epic ai-1).
`ai-dotfiles install` on a project with `@fastapi` / `@typescript` /
`@playwright-e2e` etc. created a literal `**/` directory tree with
~24 garbage `AGENTS.md` files at paths like `**/*.py/AGENTS.md`,
`**/playwright.config.ts/AGENTS.md`, `**/alembic/**/*.py/AGENTS.md`.

Root cause: catalog rules carry `paths:` frontmatter containing **file
globs** (`**/*.py`, `**/*.tsx`, `**/playwright.config.ts`). Phase 2
(ai-9 `rule_classify`, ai-10 `agents_md`) assumed `paths:` are
**directory** paths and used non-normalised entries verbatim as
directory names → `upsert_rule_block` `mkdir`'d literal-glob dirs.

Deeper issue: Codex's `AGENTS.md` mechanism is **directory-nesting
only** — it has no file-glob-scoped instruction surface. A rule scoped
to a file type (`*.py`) genuinely cannot map to an `AGENTS.md` location.
Phase 2 subagent tests used synthetic directory-style `paths:`, so the
acceptance gate passed on non-representative data.

## What to do

A `paths:` entry is usable for a nested `AGENTS.md` only if it is a
**literal, glob-free directory path** (no `*`, `?`, `[`, `]`; `**` counts
as a glob). Fix the classification + targeting:

- `core/rule_classify.py` — a rule is `PATH_SCOPED` only if it has
  `paths:` and **every** entry is a glob-free directory. If any entry
  contains a glob metacharacter → the rule is `DESCRIPTION_ONLY`
  (rendered as a Codex-only `rule-<name>` skill — the Codex-native
  description-triggered fallback). All-or-nothing keeps it predictable.
- `core/agents_md.py` — `rule_block_targets` must defensively reject /
  skip any glob entry so it can never `mkdir` a literal-glob directory,
  even if mis-called.
- Verify the wiring (`codex_install` / `codex_targets`) routes a
  now-`DESCRIPTION_ONLY` rule to the skill path.
- Tests must use the **real catalog rule shapes**: `paths: ["**/*.py"]`,
  mixed `paths: ["**/tests/e2e", "**/*.spec.ts"]`, and a literal
  `paths: ["backend"]`. Assert `install` never creates a `**` or other
  glob-named directory.

## Acceptance criteria

- [x] A rule whose `paths:` contains any glob is classified `DESCRIPTION_ONLY` and renders as a `rule-<name>` Codex skill.
- [x] A rule whose `paths:` are all glob-free directories still renders nested `AGENTS.md` in those dirs.
- [x] `rule_block_targets` / `upsert_rule_block` never create a directory whose name contains a glob metacharacter.
- [x] A regression test installs a glob-`paths` rule and asserts no `**` / glob-named directory appears in the project.
- [x] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green (951 passed; mypy 59 files; ruff + black clean).
- [x] PR opened against `main` — [#9](https://github.com/pavel-gorlov/ai-dotfiles/pull/9), merged.

## Anti-patterns

- Half-applying a mixed rule (some dirs, some globs) — render the whole
  rule one way. All-or-nothing → `DESCRIPTION_ONLY` if any glob.
- Testing only with synthetic directory `paths:` — the bug hid exactly
  there. Use real catalog rule shapes.
