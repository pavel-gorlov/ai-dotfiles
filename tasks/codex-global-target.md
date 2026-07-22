# Feature: Codex global (user-scope) target

> **Status:** implemented (2026-07-19) — code, tests and docs landed per the
> plan below. Q4 verified empirically on Codex CLI 0.143: no de-duplication,
> both scope variants of a same-named skill appear in the session prompt
> (recorded in the builtin skill doc). Acceptance 2 verified with
> `codex debug prompt-input` + isolated `CODEX_HOME`: a globally-installed
> skill, the rule block and the `CLAUDE.md` bridge all load in a neutral
> project.
> Prior art: PR #13 (`feat/codex-local-migration`) shipped the project-scope
> equivalent — read `core/codex_migrate.py` + `core/codex_reconcile.py` first;
> the global version is the same shape with a different root.

## Goal

Let globally-installed packages (`ai-dotfiles install -g` / `add -g`) also
render to OpenAI Codex's **user scope**, so a global skill/agent/rule is
available in every Codex session without being added to each project manifest.

Opt-in via `"targets"` in `~/.ai-dotfiles/global.json`; default stays
`["claude"]` (no behaviour change until asked for).

## Why

The Codex target is project-scoped only today (ADR ai-1-3). `install -g` /
`add -g` / `status -g` force `["claude"]`, and there is no global Codex path
function at all — `core/paths.py` exposes only `claude_global_dir()`, while
every Codex path takes a project root.

Verified: `install -g` never creates `~/.codex` or `~/.agents`, **even with
`"targets":["codex"]` hand-written into `global.json`** (the flag is ignored in
the global scope). Consequence: the only way to use a catalog element in Codex
is to add it to every project's manifest with `targets: ["codex"]` — exactly
the duplication the global scope exists to avoid.

## Verified platform facts (Codex CLI 0.143.0 — do NOT re-research)

Established empirically with `codex debug prompt-input` (renders the
model-visible prompt, no model call), run in a *neutral* project that had no
project-local skills, with an isolated `CODEX_HOME`:

| Surface | Result |
|---|---|
| `$CODEX_HOME/skills/<name>` as a **symlink** to a real skill dir | loads ✅ |
| `~/.agents/skills/<name>` as a **symlink** | loads ✅ |
| `$CODEX_HOME/AGENTS.md` (global instructions) | loads ✅ |

Carried over from the project-scope work (already verified, see PR #13):

- Codex enforces a **hard 1024-char cap** on a skill's frontmatter
  `description`; over the cap the *whole skill fails to load*
  (openai/codex#13941). Three skills in the current catalog already exceed it.
- Symlinking a skill **directory** works; symlinking the `SKILL.md` **file**
  does not (the walker skips symlinked files).
- Agent `.toml` symlink-following is version-unstable → render, don't symlink.
- `project_doc_fallback_filenames` is honoured at user scope too.

## Scope to plan

Mirror the shipped project-scope design onto the user scope:

| Element | Global Codex target | Strategy |
|---|---|---|
| skill | `$CODEX_HOME/skills/<name>` | gated symlink (description ≤ 1024 **and** valid hyphen-case name), else render with the first-sentence trim |
| agent | `$CODEX_HOME/agents/<name>.toml` | render + `# source-sha256` drift header |
| rule | `$CODEX_HOME/AGENTS.md` block (always-on) or `rule-<name>` skill | dispatch by `RuleClass`, as today |
| global `CLAUDE.md` | `$CODEX_HOME/AGENTS.md` | bridge — see open question 2 |
| domain settings / MCP | `$CODEX_HOME/config.toml` | managed `[ai_dotfiles]` + `[mcp_servers]` |
| domain hooks | `$CODEX_HOME/hooks.json` | translate via `core/codex_hooks.py` |

Also in scope: `status -g` reports the Codex global target; `remove -g` strips
symmetrically.

## Constraints / gotchas

- **`~/.codex/config.toml` and `~/.codex/hooks.json` are already occupied** —
  by the user's own settings and by moshi's `moshi-hook` entries. Writing there
  MUST preserve foreign content: reuse the existing ownership discipline
  (managed-region markers for `config.toml`, per-group signature sidecar for
  `hooks.json`). This is a sharper risk than in the project scope, where the
  files are usually ours alone.
- Respect **`CODEX_HOME`** — do not hardcode `~/.codex`, the same way
  `storage_root()` respects `AI_DOTFILES_HOME`.
- The 1024-char gate must apply globally too: a bare symlink of an over-cap
  catalog skill silently breaks that skill for every project.
- A global rule block in `$CODEX_HOME/AGENTS.md` needs the same marker + prune
  symmetry as project blocks and must not clobber a user-authored global
  `AGENTS.md`.

## Reuse map (most of this exists — extend, don't rewrite)

- `core/paths.py` — add `codex_global_*` path functions. This is the only
  genuinely missing primitive.
- `core/codex_render.py`, `core/codex_install.py` — render/apply are already
  source/target-path agnostic; reuse unchanged.
- `core/codex_migrate.py` — holds the gated-symlink logic for skills
  (`_skill_symlink_ok`, `_relative_symlink`); factor out for shared use.
- `core/codex_config.py`, `core/codex_hooks.py` — writers already take a root
  and own a managed region + ownership sidecar; parameterise the root.
- `core/codex_targets.py` — `iter_codex_pairs` / `iter_codex_rule_plans` take
  `(element, root, catalog)`; pass the global root.
- `commands/install.py::_install_global`, `commands/add.py`,
  `commands/remove.py`, `commands/status.py` — the `-g` paths currently force
  `["claude"]`; that is the gate to open.

## Acceptance criteria

1. `global.json` with `"targets": ["claude","codex"]` + `install -g` renders the
   global packages into the Codex user scope. **Without** the flag, behaviour is
   byte-identical to today.
2. A globally-installed skill is visible in a Codex session in an arbitrary
   project with no project-level config (verify with `codex debug prompt-input`
   and an isolated `CODEX_HOME`).
3. `remove -g` strips only ai-dotfiles-owned entries: a hand-authored
   `~/.codex/config.toml` key, a user hook group, and a user-authored paragraph
   in the global `AGENTS.md` all survive.
4. `status -g` reports the Codex global artefacts (OK / STALE / NOT INSTALLED).
5. Full suite green; `mypy --strict` clean.

## Open questions for the planner

1. **Skills dir:** `$CODEX_HOME/skills/` (respects `CODEX_HOME`) vs
   `~/.agents/skills/` (HOME-relative). Both verified to work; recommendation is
   the former.
2. **Global `CLAUDE.md` → `$CODEX_HOME/AGENTS.md`:** symlink (zero drift, but
   the file can then not also hold rule blocks) vs a managed block rendered into
   a real `AGENTS.md` (composes with rule blocks, needs drift tracking).
3. Should global rule blocks and the instruction bridge **share**
   `$CODEX_HOME/AGENTS.md`? If yes, the symlink option in (2) is ruled out.
4. **Duplication:** an element installed both globally and in a project renders
   twice (user scope + project scope). Is that harmless (does Codex de-dupe by
   skill name?) or should one win? Needs a decision and probably a test.
5. Does `reconcile` grow a `-g` mode, or does global drift detection live only
   in `status -g`?

---

# PLAN

## Decisions (answers to the open questions)

> Confirmed interactively with the user on 2026-07-18 — including the two
> follow-up decisions (path-scoped demotion, global
> `project_doc_fallback_filenames`). These are settled, not proposals.

1. **Skills dir → `$CODEX_HOME/skills/`.** It follows `CODEX_HOME` (constraint
   above), and keeps every global artefact under one root; `~/.agents/` ignores
   the env var and splits the tree.
2. **Global `CLAUDE.md` bridge → managed block, not symlink.** A symlink would
   monopolise `$CODEX_HOME/AGENTS.md` (no rule blocks, clobbers user-authored
   content — forbidden by the constraints). Render `~/.claude/CLAUDE.md`'s body
   into a managed block named `claude-global-instructions`, reusing the
   `core/agents_md.py` block machinery (`upsert_rule_block` /
   `block_matches` / `strip_rule_blocks`) — the embedded `sha256` marker line
   gives drift detection for free. The name is reserved: a catalog rule may not
   claim it.
3. **Yes — shared file.** Rule blocks and the instruction bridge both live as
   managed blocks in a real `$CODEX_HOME/AGENTS.md`; user paragraphs around
   them are preserved by the existing marker discipline.
4. **Duplication: accept it.** The global scope cannot know every project, so
   de-duping at install time is impossible by construction. Expected Codex
   behaviour is project-scope shadowing by name; verify empirically during
   implementation (`codex debug prompt-input`, same skill in both scopes) and
   record the observed behaviour in the builtin skill doc + a test.
5. **`reconcile -g`: yes.** Once `codex_reconcile` is layout-parameterised the
   `-g` mode is nearly free, and it keeps the status/reconcile symmetry (status
   reports drift, reconcile fixes it — in both scopes).

Additional decisions the plan needs:

- **Path-scoped rules at global scope** have no per-directory `AGENTS.md`
  surface (there is no project tree). Demote them to a synthetic `rule-<name>`
  skill (same path glob-carrying rules already take) and `ui.warn` about the
  demotion. `ALWAYS_ON` → block in `$CODEX_HOME/AGENTS.md`.
- **Global skill symlinks are absolute**, matching the global Claude
  convention (`symlinks.py:133` links `source_abs`). `$CODEX_HOME` and
  `AI_DOTFILES_HOME` move independently, so migrate's *relative* links are
  wrong here. Prune identifies our symlinks by "resolves under
  `catalog_dir()`" (rendered artefacts keep the existing managed markers).
- **`project_doc_fallback_filenames` is also set in `$CODEX_HOME/config.toml`**
  (gated on the codex target): one write makes every CLAUDE.md-only project
  readable by Codex, mirroring what `migrate` does per-project. Additive and
  idempotent via `ensure_project_doc_fallback`.

## Implementation plan

### Stage 0 — missing primitives (`core/paths.py`, new `core/codex_layout.py`)

- `paths.codex_home() -> Path`: `CODEX_HOME` env override, else `~/.codex` —
  mirror `storage_root()` (paths.py:15-24).
- `paths.project_codex_dir(root) -> Path` = `root/".codex"` — replaces the
  `.codex` hardcoding currently repeated in `codex_config.config_path`,
  `codex_hooks.hooks_path` and `codex_local_registry.registry_path`.
- New `core/codex_layout.py`:

  ```python
  @dataclass(frozen=True)
  class CodexLayout:
      skills_dir: Path        # project: <root>/.agents/skills   global: $CODEX_HOME/skills
      agents_dir: Path        # project: <root>/.codex/agents    global: $CODEX_HOME/agents
      codex_dir: Path         # project: <root>/.codex           global: $CODEX_HOME
      root_agents_md: Path    # project: <root>/AGENTS.md        global: $CODEX_HOME/AGENTS.md
      project_root: Path | None   # None ⇒ global scope (drives rule dispatch)
  ```

  with constructors `project_layout(root)` / `global_layout()`. A separate
  module avoids import cycles (codex_targets, codex_config, agents_md callers
  all need it).

### Stage 1 — parameterise the core (pure refactor, no behaviour change)

- `core/codex_targets.py`: `iter_codex_pairs` / `iter_codex_rule_plans` take a
  `CodexLayout` instead of `project_root`. Rule dispatch: with
  `layout.project_root is None`, `PATH_SCOPED` produces a rule-skill *pair*
  (demotion) instead of a plan; `ALWAYS_ON` plans target
  `[layout.root_agents_md]`. Update all call sites: `commands/install.py`,
  `add.py:120,127`, `remove.py:160,165`, `status.py`, `codex_migrate.py:231,247`,
  `codex_reconcile.py`.
- `core/elements.py::resolve_target_paths` Codex branch duplicates this path
  logic (`_codex_pair_for`) — delegate it to `codex_targets` so the layout
  lives in one place.
- `core/codex_config.py`, `core/codex_mcp_ownership.py`, `core/codex_hooks.py`:
  writers take `codex_dir: Path` instead of `project_root` (project call sites
  pass `paths.project_codex_dir(root)`, global passes `paths.codex_home()`).
  `config_path`, `hooks_path`, ownership-sidecar paths follow.
- `core/codex_migrate.py`: factor the gated-symlink core out for shared use —
  move `_skill_symlink_ok` / `_valid_skill_name` to `codex_install` as public
  `skill_symlink_ok(source_dir, name)`; consolidate `_relative_symlink` into a
  `codex_install.symlink_codex_skill(source, target, *, relative: bool)`
  (migrate keeps `relative=True`; global uses `relative=False`).
  `SKILL_DESCRIPTION_MAX` stays importable from `codex_migrate`.
- Gate: full suite green after this stage with zero test edits (except moved
  private-helper tests re-pointed at the new public home).

### Stage 2 — global install / add / remove

- `commands/install.py::_install_global`: read
  `targets = manifest.get_targets(manifest_path)` (absent ⇒ `["claude"]`, so
  default behaviour stays byte-identical); after the Claude work,
  `if "codex" in targets: _install_codex_global(parsed, packages, catalog, prune=prune)`.
- New `_install_codex_global` mirrors `_install_codex_target`
  (install.py:408-473) with `global_layout()`:
  - **skills**: `skill_symlink_ok` → absolute symlink to the catalog dir, else
    `install_codex_skill` render (first-sentence trim). Track wanted paths for
    prune.
  - **agents**: `install_codex_agent` (sha header as today).
  - **rules**: dispatch per the decisions above
    (`apply_codex_rule_blocks` → `$CODEX_HOME/AGENTS.md`; rule-skills incl.
    demoted path-scoped, with a warn).
  - **instructions bridge**: if `claude_global_dir()/"CLAUDE.md"` exists,
    `upsert_rule_block(root_agents_md, "claude-global-instructions", body)`.
  - **config/mcp/hooks**: existing writers with `codex_dir=paths.codex_home()`
    + `ensure_project_doc_fallback(..., "CLAUDE.md")`. The managed-region /
    signature-sidecar discipline is what protects the user's own
    `~/.codex/config.toml` keys and moshi's hook groups — no new mechanism.
  - **prune** (`--prune`): walk `$CODEX_HOME/skills|agents` — remove unwanted
    *managed* renders (existing `remove_codex_*`) and unwanted *symlinks that
    resolve under `catalog_dir()`*; strip unwanted rule blocks **only from
    `$CODEX_HOME/AGENTS.md`** (do NOT reuse the project `rglob` prune — never
    walk `$HOME`), keeping the bridge block while its source `CLAUDE.md`
    exists.
- `commands/add.py` / `remove.py`: drop the forcing at add.py:218 /
  remove.py:339 → `manifest.get_targets(manifest_path)` in both scopes; the
  codex branches use `global_layout()` when `project_root is None`. `remove -g`
  unlinks/strips symmetrically and rebuilds config/hooks from the remaining
  packages; it does not touch the instructions bridge (owned by install).
- Update the ADR ai-1-3 comments at those sites (decision superseded by this
  task).

### Stage 3 — `status -g` and `reconcile -g`

- `commands/status.py`: replace the `and not is_global` gate (status.py:485)
  with layout-aware reporting. Global additions on top of the existing
  OK / STALE / NOT INSTALLED classification:
  - symlinked skill → OK when the link resolves into the catalog; **re-run
    `skill_symlink_ok` on the source** and report
    `STALE (description now over cap — re-render)` if it no longer qualifies
    (a silently-broken skill otherwise, per constraint 3);
  - bridge block → `block_matches` vs the current `~/.claude/CLAUDE.md` body;
  - config → `config_state` with the global `codex_dir`.
- `commands/reconcile.py`: add `-g/--global` (no project root required).
  Global mode = catalog side of `codex_reconcile.reconcile_codex` with
  `global_layout()` (`include_catalog = "codex" in global targets`; no
  local-registry side — `migrate` does not exist at global scope) + refresh of
  bridge block and config. Symlink-eligibility change (skill went over the
  1024 cap) reconciles symlink → render. `--check` semantics unchanged.

### Stage 4 — tests

- `tests/conftest.py`: add `tmp_codex_home` fixture
  (`monkeypatch.setenv("CODEX_HOME", ...)`) alongside the existing
  HOME / `AI_DOTFILES_HOME` isolation; codex-global tests always use it (never
  touch the real `~/.codex`).
- unit: `codex_home()` env override + default; `CodexLayout` constructors;
  `skill_symlink_ok` in its new home; global rule dispatch (path-scoped
  demotion).
- integration:
  - `install -g` with `targets: ["claude","codex"]`: under-cap skill →
    absolute symlink in `$CODEX_HOME/skills`; over-cap skill → render + trim +
    sidecar; agent `.toml` + sha header; always-on rule block and bridge block
    in `$CODEX_HOME/AGENTS.md`; config managed region; hooks group written.
  - **foreign-content survival** (acceptance 3): pre-seed a user
    `config.toml` table, a moshi-like hook group, and a user paragraph in
    `AGENTS.md` → `install -g` + `remove -g` preserve all three.
  - **byte-identical default** (acceptance 1): `install -g` without `targets`
    creates nothing under `$CODEX_HOME`.
  - prune: orphaned managed render/symlink removed; user-authored skill dir
    and unrelated symlinks untouched.
  - `reconcile -g`: stale render regenerated; over-cap flip converts
    symlink → render; `--check` exits non-zero on drift, writes nothing.
- e2e (CliRunner): `status -g` shows the Codex section with OK / STALE /
  NOT INSTALLED (acceptance 4); `remove -g` symmetry.

### Stage 5 — docs (same PR, per project policy)

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`: replace
  the "Codex is project-scoped only" statement (line ~166), extend the targets
  section with the global scope, document `CODEX_HOME`, what `install -g`
  produces, and the duplication behaviour observed in (Q4).
- `CLAUDE.md` + `AGENTS.md`: extend the Codex sections with the global target.
- This file: move to `tasks/done/` on completion; note that ADR ai-1-3's
  "project-scoped only" is superseded.

### Verification

1. `poetry run pytest --cov` (≥ 80 %), `poetry run mypy src/` (strict),
   `ruff check`, `black --check`, `pre-commit run --all-files` (acceptance 5).
2. Platform check (acceptance 2): isolated `CODEX_HOME` + neutral project;
   `install -g` with the codex target; `codex debug prompt-input` shows the
   globally-installed skill. Same run answers Q4 (skill present in both
   scopes) — record the result.
3. Acceptance 3 rehearsal happens in the integration tests only — never
   against the real `~/.codex`.

### Risk notes

- The Stage 1 signature changes (`project_root` → `codex_dir`/layout) fan out
  across ~8 core modules and 5 commands — do it in one commit; `mypy --strict`
  catches any missed call site.
- The single sharpest hazard is global prune walking too wide: the project
  implementation `rglob`s `AGENTS.md` under the root — reusing that with a
  home-derived root would crawl the user's home. The global prune touches
  exactly three places: `$CODEX_HOME/skills`, `$CODEX_HOME/agents`,
  `$CODEX_HOME/AGENTS.md`.
- `claude-global-instructions` shares the rule-block marker namespace;
  reserve the name (refuse a catalog rule with that stem at global install).
