## v0.3.0 (2026-08-13)

### Feat

- **codex**: translate permission lists into the Codex exec policy

### Fix

- **codex**: stop carrying Claude model pins into Codex agents

## v0.2.0 (2026-08-11)

### Feat

- **codex**: add global (user-scope) Codex target

### Fix

- **runtime**: resolve home dir in bin shims at runtime

## v0.1.0 (2026-07-29)

### BREAKING CHANGE

- `ai-dotfiles stack ...` is removed. Replace each stack
with a meta-domain (a `domain.json` whose only field is `depends`), and
install it via `add @<name>` / `install`.

### Feat

- **status**: surface local elements and Claude-only surfaces
- **codex**: emit domain hooks to .codex/hooks.json
- **codex**: add `reconcile` to refresh stale/missing Codex artefacts
- **codex**: add `migrate` for local (non-catalog) project elements
- **core**: discover local (non-catalog) project elements
- **ai-21**: link_mode copy for the Claude target (native-Windows hosts)
- **ai-17**: wire .codex/config.toml into the add command
- **ai-15**: translate mcp.fragment.json to .codex/config.toml [mcp_servers]
- **ai-14**: translate settings.fragment.json to .codex/config.toml
- **ai-11**: wire rules into the Codex target
- **ai-10**: AGENTS.md assembly for Codex rules
- **ai-9**: rule classification for the Codex target
- **ai-5**: wire install/add/remove/status for the Codex target
- **ai-4**: Codex render layer (agent TOML + skill SKILL.md)
- **ai-3**: core scaffolding for multi-target support
- **vendor**: add printingpress skills marketplace
- **vendor**: add mattpocock skills marketplace
- **domain**: provision per-domain venv and bin shims on install
- **list**: mark installed packages in list and list --available
- drop stack command — meta-domains replace it
- **cli**: auto-manage .gitignore for vendored symlinks (#1)
- **mcp**: domain mcp.fragment.json -> .mcp.json
- **cli**: `install --prune` removes dangling catalog symlinks
- **cli**: add `pull` to sync storage from its git remote
- **cli**: `list` shows project and global scopes side-by-side
- **cli**: extend tab completion to domain, stack, create_delete, vendor remove
- **cli**: tab-complete packages for add/remove and stacks for stack apply
- **core**: add completions helpers for catalog/manifest/stacks lookups
- **cli**: add `completion` command for bash/zsh tab completion
- **cli**: add 'ai-dotfiles update' for CLI-managed files in storage
- **skill**: enrich ai-dotfiles SKILL frontmatter with when_to_use and paths
- **init**: adopt existing ~/.claude/ files on `init -g` instead of backing up
- **vendor**: unified search + install URLs in list
- **scaffold**: ship builtin `ai-dotfiles` skill on init -g
- **vendors**: add buildwithclaude and tonsofskills (Q1, Q2)
- **vendors**: add shared git-repo cache + refresh CLI (Q0)
- **vendors**: add paks vendor (P2)
- **npx_skills**: add 'find' subcommand for marketplace search
- rewrite vendor CLI as click group (V4)
- add github and npx_skills vendor plugins (V2, V3)
- add core vendor framework (V1)
- wire all commands into CLI (Step 9)
- add primary, secondary, and vendor commands (Steps 4-8)
- add core modules + scaffold (Steps 2 & 3)
- add project skeleton (Step 1)

### Fix

- **status**: report stale Codex config.toml drift
- **status**: detect stale Codex rule blocks by sha, not just presence
- **ai-20**: Codex target copies skill support files instead of symlinking
- **ai-19**: generated SKILL.md starts with frontmatter; drift meta moves to sidecar
- **ai-18**: glob paths: entries no longer create literal-glob AGENTS.md dirs
- **remove**: warn when bin shim is dropped on global remove (#3)
- **paths**: handle deleted CWD with PWD fallback
- **domain**: auto-link new elements when domain is already installed
- **vendor**: correct paks.stakpak.dev URL path prefix
- **mcp**: self-healing write order and post-crash install recovery
- **test**: set repo-local committer identity in pull fixture
- **skill**: drop 'paths' field — it restricts activation, not expands it
- **skill**: flatten when_to_use to a single-line scalar
- **paks**: align with real paks 0.1.18 CLI behaviour
- **npx_skills**: handle real upstream output and install flags

### Refactor

- **core**: introduce domain.json with first-class transitive deps
- **vendor**: drop DESCRIPTION column from aggregated search output
- **vendors**: rename 'find' -> 'search' (P1)
- **vendors**: simplify Dependency schema, drop deps install (P0)
- **vendors**: rename npx_skills -> skills_sh
