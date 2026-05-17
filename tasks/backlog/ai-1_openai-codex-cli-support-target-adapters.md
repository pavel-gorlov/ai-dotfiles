---
id: ai-1
kind: epic
status: backlog
created_at: '2026-05-16T19:37:06+00:00'
success_metrics:
- 'A manifest with `"targets": ["codex"]` produces a working `.agents/skills/` (generated `SKILL.md` + symlinked support files) and committed `.codex/agents/*.toml` after `ai-dotfiles install`.'
- Every existing Claude-only manifest (no `targets` field) installs byte-identically — zero regression.
- '`ai-dotfiles status` flags a generated Codex agent as stale when its source `.md` changed.'
- Codex-target code carries test coverage at or above the project threshold (>= 80%).
out_of_scope:
- Codex custom prompts (`~/.codex/prompts/`) — global-only in Codex, no per-project surface, no catalog element maps to them.
- Codex hooks — Codex has no hook harness.
- A standalone `migrate` command porting an existing `.claude/` tree to `.agents/` — the catalog is the source of truth, rendering is enough.
- Gemini CLI / Cursor / other targets — the adapter layer is built so they can be added later, but they are not in this epic.
- Bidirectional sync (editing `.codex/agents/*.toml` and propagating back to the catalog) — generation is one-way, catalog -> target.
- Multi-target global install — the Codex target is project-scoped only; `~/.ai-dotfiles/global.json` and `install -g` stay Claude-only.
---

# OpenAI Codex CLI support (target adapters)

## Why

Codex CLI and Claude Code now share the Agent Skills open standard:
`SKILL.md` is byte-identical across both. But the *plumbing* differs —
different directories, agents as TOML instead of Markdown, instructions
in `AGENTS.md` instead of `CLAUDE.md`. The user wants to experiment with
Codex without forking the catalog or hand-porting every element.

Today every ai-dotfiles command writes to Claude Code paths
(`~/.claude/`, `<project>/.claude/`). The catalog is already the single
source of truth — what is missing is a *rendering layer*: per-target
knowledge of where files go and what format they take. This epic adds
that layer and makes Codex CLI a first-class target alongside Claude
Code, sharing one catalog and one manifest.

## Goal and success metrics

Make ai-dotfiles a multi-target package manager. A project manifest
declares its targets:

```json
{ "packages": ["@gitflow", "skill:commit"], "targets": ["claude", "codex"] }
```

and `ai-dotfiles install` / `add` / `remove` render each package for
*every* listed target. A missing `targets` field means `["claude"]` —
every existing manifest keeps working unchanged.

Success metrics: see frontmatter `success_metrics`.

### The Codex CLI surface

| Element        | Global                          | Project                       | Format |
|----------------|---------------------------------|-------------------------------|--------|
| Instructions   | `~/.codex/AGENTS.md`            | `AGENTS.md` (walked root->cwd) | Markdown |
| Skills         | `~/.agents/skills/<name>/`      | `.agents/skills/<name>/`      | dir + `SKILL.md` (frontmatter `name`, `description`) |
| Subagents      | `~/.codex/agents/<name>.toml`   | `.codex/agents/<name>.toml`   | TOML (`name`, `description`, `developer_instructions` + optional `model`, `sandbox_mode`) |
| Custom prompts | `~/.codex/prompts/<name>.md`    | global-only                   | Markdown |
| Config / MCP   | `~/.codex/config.toml`          | `.codex/config.toml`          | TOML, `[mcp_servers]` section |

Mapping consequences:

- **skill** — `SKILL.md` is the shared open standard, but the Codex skill
  list is byte-capped (~8000 chars), so `SKILL.md` is *regenerated* with a
  trimmed (first-sentence) `description`; the rest of the skill directory
  (`scripts/`, `references/`, `assets/`) is symlinked. Drift-tracked like
  agents (`# source-sha256`).
- **agent** — catalog agents are `.md` + YAML frontmatter; Codex wants
  `.toml`. **Conversion required.** The result is a *generated* file, so
  it cannot be a symlink — it is written, committed, and tracked.
- **rule** — Claude Code loads `.claude/rules/*.md` by `description`.
  Codex offers two activation mechanisms; rules split three ways
  (see Phase 2).
- **hooks** — Codex has no hook harness. Dropped for the Codex target;
  `install` logs the skip rather than failing silently.

Verified against the Codex CLI docs (May 2026):
[skills](https://developers.openai.com/codex/skills),
[subagents](https://developers.openai.com/codex/subagents),
[customization](https://developers.openai.com/codex/concepts/customization),
[AGENTS.md](https://developers.openai.com/codex/guides/agents-md),
[custom prompts](https://developers.openai.com/codex/custom-prompts).
Migration practice (classify, do not copy the file tree):
[Blake Crosley](https://blakecrosley.com/blog/claude-code-to-codex-migration),
[Codex Blog](https://codex.danielvaughan.com/2026/03/26/migrating-claude-code-to-codex-cli/),
[AgentLint](https://www.agentlint.app/blog/claude-md-to-agents-md-migration-guide/).
The Codex surface above is a docs snapshot (May 2026) — re-verify on the
next Codex CLI minor release before Phase 2/3.

### Alternatives considered

- **Target selection.** A `--target` flag (per-command, trivially
  desynced across `add`/`install`) and a mirrored `ai-dotfiles codex`
  command namespace (duplicates the whole command surface) both lost to
  the manifest `targets` field — one manifest, configs stay in sync.
- **Skill `description` cap.** Measure-then-trim (trim only when over
  budget) lost to always-trim (ADR ai-1-4) — a conditional that behaves
  differently per catalog state is harder to reason about than a
  predictable render.
- **Description-only rule.** A managed block in root `AGENTS.md` lost to
  a Codex-only skill (ADR ai-1-2) — Codex skills *are* the native
  description-triggered, progressive-disclosure analogue of a Claude rule.

## Out of scope

See frontmatter `out_of_scope`.

## Phases

Three phases. Phase 1 is the MVP (skills + agents in a project). Phases
2-3 follow once Phase 1 lands and is reviewed. Subtask files (`ai-1/`)
are written by `breakdown-feature` *after* this plan is approved.

### Phase 1 — skills + agents, project-scoped (the MVP)

The `targets` mechanism, the target-adapter layer, skill symlinking, and
agent MD->TOML conversion. After this phase a project with
`"targets": ["codex"]` gets working `.agents/skills/` and `.codex/agents/`.
Ships as one PR (`feat: Codex CLI target support`).

| Subtask | Scope |
|---------|-------|
| Core scaffolding | `core/frontmatter.py` — extract the YAML-frontmatter parser duplicated in `dependencies.py`; `core/targets.py` — `Target` enum + per-`ElementType` render policy; `core/paths.py` — `project_codex_skills_dir()`, `project_codex_agents_dir()`; `core/manifest.py` — `get_targets()`; `elements.py` — make `resolve_target_paths` target-aware. Pure `core/`, no command wiring. |
| Render layer | `core/codex_render.py` — `render_agent_toml(md_path)` (frontmatter -> `name`/`description`/`model`, body -> `developer_instructions`) and `render_skill_md(md_path)` (trimmed first-sentence `description`); both emit a `# managed-by` + `# source-sha256` header; add `tomli-w` dependency (chosen over hand-rolled TOML for correct string escaping — note `tomli-w` emits no comments, so the header is prepended as raw text). |
| Wire commands | `install` / `add` / `remove` iterate `targets`; Codex skill = generated `SKILL.md` + symlinked support files, agent = rendered `.toml`; `status` drift detection; `--prune` cleans managed files. |
| Tests | Integration + e2e: `.agents/skills` symlinks, `.codex/agents` generation, drift detection, multi-target install. |
| Docs | Builtin skill (`builtin_ai_dotfiles_skill.md`: `targets`, Codex behaviour), README, project `CLAUDE.md` maintenance note. |

`Core scaffolding` -> `Render layer` -> `Wire commands` share files and run
**sequentially**; `Tests` and `Docs` follow.

### Phase 2 — rules -> Codex (AGENTS.md + Codex-only skills)

Rules classify three ways by frontmatter:

- **always-on** (`engineering-principles`, `python`, ...) -> managed
  block appended to the project-root `AGENTS.md`.
- **path-scoped** — new optional rule frontmatter field `paths:`
  (directory globs) -> managed block written to `<dir>/AGENTS.md`; Codex
  activates it via its root->cwd walk. This is the "conditional rules
  that activate by path" requirement.
- **description-only** (no `paths:`, not always-on) -> rendered as a
  synthetic **Codex-only skill** under `.agents/skills/`.

| Subtask | Scope |
|---------|-------|
| Rule classify | Rule frontmatter `paths:` field + classifier (`always-on` / `path-scoped` / `description-only`). |
| AGENTS.md assembly | `core/agents_md.py` — assemble `AGENTS.md` (root + nested) with marker-delimited managed blocks; `strip_owned` analogue so `remove` touches only its own blocks. |
| Wire rules | Render description-only rules as Codex-only skills; wire rules into `install`/`remove` for the Codex target; tests. |
| Docs | Builtin skill, README, rule-authoring note. |

### Phase 3 — config.toml + MCP

| Subtask | Scope |
|---------|-------|
| config.toml | `settings.fragment.json` -> partial `config.toml` map (permissions/sandbox; hooks dropped with a logged skip). |
| MCP | `mcp.fragment.json` -> `[mcp_servers]` in `.codex/config.toml`. |
| Docs | Builtin skill, README. |

Phases 2 and 3 are separate PRs after Phase 1 review.

## Decisions

Resolved with the user during planning:

- **ADR ai-1-1 (generated agent TOML is committed).** The generated
  Codex `.toml` is a real project artefact and is committed, not
  git-ignored. To stop it drifting from its source `.md`: the file
  carries a `# managed-by: ai-dotfiles` header plus a
  `# source-sha256: <hash>` of the source agent's content; `status`
  flags a stale generated agent when the hash mismatches (fail-loud,
  enforced by mechanics); `install` / `update` regenerate stale agents;
  a maintenance note is added to the project `CLAUDE.md`.
- **ADR ai-1-2 (description-only rule -> Codex-only skill).** A rule
  with no path scope and not always-on is rendered as a Codex skill
  (Codex skills are description-triggered with progressive disclosure —
  the exact analogue of a Claude rule). This synthetic skill is wired
  into the Codex target only; never installed for the Claude target.
  It is named `rule-<name>` to avoid colliding with a real catalog skill.
- **ADR ai-1-3 (target selection via `targets` field).** The manifest
  `targets` array selects targets; absent => `["claude"]`. The global
  manifest does **not** get a `targets` field — the Codex target is
  project-scoped only (see `out_of_scope`).
- **ADR ai-1-4 (Codex skill render always trims `description`).** Codex
  caps the skill list at ~8000 chars; rather than measure-then-decide,
  the Codex render *always* emits `SKILL.md` with a first-sentence
  `description` (trigger phrases dropped). Consequence: Codex skills are
  not pure symlinks — `SKILL.md` is generated, support files symlinked.
- **ADR ai-1-5 (`settings.fragment.json` -> partial `config.toml`).**
  The Codex target maps the translatable keys (permissions, sandbox)
  into `config.toml` and skips the rest (hooks) with an explicit
  fail-loud message in `install` output.

Promote to `tasks/decisions/ai-1-N.md` files if any decision grows
non-trivial during breakdown.

## Resolved during review

All four planning questions were resolved with the user (2026-05-17):
partial settings map with logged skips (ADR ai-1-5); Codex render always
trims skill descriptions (ADR ai-1-4); global stays project-scoped /
Claude-only (ADR ai-1-3, `out_of_scope`); synthetic skills named
`rule-<name>` (ADR ai-1-2). The epic is ready for `breakdown-feature`.
