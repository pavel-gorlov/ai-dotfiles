# ~/.ai-dotfiles

Storage for `ai-dotfiles` — a package manager for Claude Code, Codex and
DeepSeek Harness configuration. `AI_DOTFILES_HOME` can select another location.

## Quick start

1. `ai-dotfiles init` — initialize a project manifest
2. `ai-dotfiles add skill:my-skill` — add an element
3. `ai-dotfiles install` — refresh the project's selected targets

The default target remains Claude. To opt into other targets, edit the project's
`ai-dotfiles.json` or this directory's `global.json`:

```json
{"packages": [], "targets": ["claude", "codex", "dsh"]}
```

Keep your existing `packages`; choose only the targets you want. `add` installs
immediately, `remove` rebuilds remaining contributions, and `status` reports
drift. `reconcile --check` writes nothing and exits non-zero on drift;
`reconcile` refreshes it. Use `-g` on `install`, `add`, `remove`, `status` and
`reconcile` for the global manifest. `install --prune` retires proven owned
stale outputs. Vendor installs, `update` and `pull` update the catalog; run
`install` in consumers and restart managed DSH to use changed sources.

## Layout

```
~/.ai-dotfiles/
├── global/          # files symlinked into ~/.claude/
├── global.json      # global package manifest
├── catalog/         # installable content (domains + standalone)
└── README.md
```

`global/` remains the Claude source directory. Selected global Codex outputs use
`$CODEX_HOME` (default `~/.codex`); DSH outputs use `$DSH_HOME` (default `~/.dsh`).
Project DSH skills/configuration live under `<manifest-root>/.dsh/`, with shared
instructions in `AGENTS.md`. Edit catalog originals, not generated resources.
DSH profiles and home patches remain user-owned.

## Managed DSH launch

Install official `@deepseek-ai/dsh@0.2.0-rc.2` and Node separately, make `dsh` and
`node` available on `PATH`, and prepare an existing native profile. From the
consuming project:

```bash
ai-dotfiles dsh launch --profile headless "review the changes"
ai-dotfiles dsh launch --profile web --port 8080 --no-open
ai-dotfiles migrate --to dsh --dry-run
```

These profile names must already exist. Headless requires a preset-free managed
composition; RC2 preset-managed headless fails with `COMPOSITION_NOT_SELECTED`.
Preset-aware Web is supported. Migration is project-only and defaults to Codex
unless `--to dsh` is supplied.

The launcher joins fresh global/project sources, preserves native profile/home
layers and audits the actual selected tree before Ready or turns. It never
installs DSH or creates/repairs profiles. Repeat `--patch PATH` before verbatim
native application arguments for explicit overlays. Native `config` patches
replace the whole config; explicit CLI patches override persisted UI settings.
Managed overlays are immutable, native HMR is disabled, and changes require a
restart. One process binds to its launching project; Web switching is not hard
isolation. Known whole-tool deny/ask policies are preserved; unrepresentable
restrictions block activation. Tool filters are not a security boundary.

## Native fragment example

The package resource `ai_dotfiles.scaffold.templates/example_dsh_fragment.json`
is a documentation example, not an automatically installed domain or profile.
From this storage directory, create a domain and copy the resource explicitly:

```bash
ai-dotfiles domain create review-tools
python - <<'PY'
from importlib.resources import files
from pathlib import Path

example = files("ai_dotfiles.scaffold.templates").joinpath("example_dsh_fragment.json")
Path("catalog/review-tools/dsh.fragment.json").write_bytes(example.read_bytes())
PY
```

Save the companion `catalog/review-tools/notice.mjs` module shown in the
[DSH guide's native fragment example](https://github.com/pavel-gorlov/ai-dotfiles/blob/main/docs/dsh-target.md#native-fragment-example),
then `ai-dotfiles add @review-tools` from a project targeting DSH and launch its
existing profile. The top-level JSON patch array inserts that plugin and replaces
its whole config in the second patch. Relative resources bind to the source's
owned copy; JSON contains no executable expressions or credentials.

The [CLI reference](catalog/skills/ai-dotfiles/SKILL.md) covers commands and vendor
workflows. The [DSH guide](https://github.com/pavel-gorlov/ai-dotfiles/blob/main/docs/dsh-target.md)
documents rules, hooks, MCP, provenance, collisions and runtime limitations.

## Shell alias

Shorter invocation:

```bash
alias adf='ai-dotfiles'
```
