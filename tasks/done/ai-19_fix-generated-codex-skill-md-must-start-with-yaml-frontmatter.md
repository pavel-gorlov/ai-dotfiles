---
id: ai-19
kind: task
status: done
created_at: '2026-05-17T18:52:21+00:00'
parent: ai-1
dependencies: []
---

# Fix: generated Codex SKILL.md must start with YAML frontmatter

## Context

Bug found in real Codex use. `render_skill_md` (ai-4, ADR ai-1-1/ai-1-4)
prepends a two-line drift header to every generated `SKILL.md`:

```
# managed-by: ai-dotfiles
# source-sha256: <hex>
---
name: ...
```

Codex (and the Agent Skills open standard) require the YAML frontmatter
to start on **line 1** (`---`). With the `#` lines before `---`, Codex's
skill parser does not recognise the frontmatter — **all 84 generated
`SKILL.md` are invisible to Codex's skill list**. The agent `.toml`
files are fine (TOML treats `#` as a comment).

Phase 1 tests asserted "header present" but never asserted "first line
is `---` / frontmatter parses" — the test encoded the implementation,
not the contract.

## What to do

A generated `SKILL.md` must start with `---` (valid frontmatter, line 1).

- `core/codex_render.py` — `render_skill_md` (and the rule-skill renderer
  `render_rule_skill_md`) must NOT prepend the `#` header. Output starts
  with the frontmatter.
- Move the drift/ownership metadata (`source-sha256`, managed marker)
  for skills to a **per-skill sidecar file** (e.g.
  `.agents/skills/<name>/.ai-dotfiles-meta` — small JSON or text). The
  sidecar's presence also marks the skill dir as ai-dotfiles-managed
  (a user-authored skill with no sidecar must never be pruned).
- `core/codex_install.py` — write the sidecar alongside the generated
  `SKILL.md`; update stale-detection and prune/remove to use the sidecar
  for skills instead of the in-file header.
- Agent `.toml` keeps its `# managed-by` / `# source-sha256` header —
  valid TOML, not broken. `is_stale` dispatches: `.toml` → header,
  skill → sidecar.
- Re-rendering must overwrite the old broken `SKILL.md` cleanly.

## Acceptance criteria

- [x] Every generated `SKILL.md` (domain skill and `rule-<name>` skill) has `---` as line 1; frontmatter parses.
- [x] Skill drift detection (`status` STALE) works via the sidecar — flips when the catalog source changes.
- [x] `remove` / `install --prune` identify managed skills via the sidecar; a user-authored skill (no sidecar) is never touched.
- [x] Agent `.toml` rendering is unchanged (header still present, valid TOML).
- [x] A test asserts the generated `SKILL.md` first line is `---` and the frontmatter is parseable — the test that would have caught this.
- [x] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green (959 passed; mypy 59 files; ruff + black clean).
- [x] PR opened against `main` — [#10](https://github.com/pavel-gorlov/ai-dotfiles/pull/10), merged.

## Anti-patterns

- Putting the markers as `x-`-prefixed frontmatter keys and hoping Codex
  tolerates unknown keys — a sidecar is zero-risk; the standard
  frontmatter is `name` + `description` only.
- Testing only "header present" again — assert the parser-visible
  contract: line 1 is `---`, frontmatter loads, `name`/`description` read.
