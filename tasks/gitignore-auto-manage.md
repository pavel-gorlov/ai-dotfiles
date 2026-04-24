# Feature: auto-manage `.gitignore` entries for vendored symlinks

Tracks GitHub issue #1. After `ai-dotfiles add @foo` the CLI creates
absolute-path symlinks under `<project>/.claude/` that point into
`~/.ai-dotfiles/catalog/`. Those symlinks must not be committed —
they're per-machine and dangling for everyone else. This feature keeps
`<project>/.gitignore` in sync with the real symlink set inside a
managed block.

## Goal

On every `add` / `remove` / `install` in a project scope, regenerate a
managed block inside `<project>/.gitignore` that lists every managed
symlink currently under `.claude/`. User-authored lines (outside the
block) are never touched. The block is self-healing: it reflects
whatever symlinks exist right now, so crashes / manual edits converge
back to the correct state on the next run.

```gitignore
# >>> ai-dotfiles managed — do not edit manually <<<
/.claude/skills/accessibility-audit
/.claude/skills/commit
/.claude/agents/git-workflow-assistant.md
# >>> end ai-dotfiles managed <<<
```

## Why

- Teammates / CI / Docker inherit dangling symlinks if these paths get
  committed.
- Current workaround is a manual `.gitignore` edit after every `add` /
  `remove`. Issue #1 reports 20 symlinks accidentally tracked in a real
  project before anyone noticed.

## Design decisions

| Question | Decision |
|----------|----------|
| Source of truth for block contents | Rescan `<project>/.claude/` for symlinks pointing into `storage_root()` via existing `is_managed_symlink`. No state file needed. |
| Block markers | Literal lines from issue #1 (`# >>> ai-dotfiles managed …` / `# >>> end ai-dotfiles managed <<<`). |
| Path format | Absolute-from-root glob: `/.claude/skills/foo`. Matches how gitignore treats leading-slash entries (root-anchored). |
| Collision with user-authored entries | Before writing a path to the managed block, check if it is already matched verbatim by a line OUTSIDE the block. If so, skip — issue #1 explicitly requires not duplicating and not removing on `remove`. |
| Opt-out | `--no-gitignore` flag on `add` / `remove` / `install` AND a top-level `"manage_gitignore": false` in `<project>/ai-dotfiles.json` or `~/.ai-dotfiles/global.json` (project wins). |
| When to skip silently | `<project>/.git` missing AND `<project>/.gitignore` missing. If either exists we manage it. |
| Global vs project scope | Feature is project-only. `-g` / `~/.claude/` has no `.gitignore` to manage; skip entirely. |
| File-turned-real | If the user replaced a symlink with a real file, `is_managed_symlink` returns False → the path drops out of the block → user can commit. Matches issue's "file fork" requirement. |
| Nested symlinks | We only list top-level symlinks under `.claude/{skills,agents,rules,hooks,output-styles}` + the top-level managed files (`CLAUDE.md`, `settings.json` if symlinked). Ignoring a directory symlink implicitly covers everything beneath it. |

## Plan

Four subtasks. Sequential — 01 produces the module 02 imports; 03
exercises 02's wiring; 04 documents the final CLI surface.

| # | Subtask | Details |
|---|---------|---------|
| 1 | `core/gitignore.py` + unit tests  | [gitignore-auto-manage/01-core-module.md](gitignore-auto-manage/01-core-module.md) |
| 2 | Wire into add/remove/install + flags/config | [gitignore-auto-manage/02-wire-commands.md](gitignore-auto-manage/02-wire-commands.md) |
| 3 | Integration + e2e tests           | [gitignore-auto-manage/03-tests.md](gitignore-auto-manage/03-tests.md) |
| 4 | Docs (skill + README)             | [gitignore-auto-manage/04-docs.md](gitignore-auto-manage/04-docs.md) |

### Execution

```
01 (core module)
   │
   v
02 (commands + flag + global config)
   │
   v
03 (integration + e2e)
   │
   v
04 (docs)
```

## Orchestrator role

- Dispatch in order 01 → 02 → 03 → 04.
- After each subtask: `poetry run pytest -q`, `poetry run mypy src/`,
  `poetry run ruff check src/ tests/`, `poetry run black --check src/
  tests/`, `poetry run pre-commit run --all-files`. Halt on failure.
- Never run subtasks in parallel — 02 modifies `commands/add.py`,
  `commands/remove.py`, `commands/install.py` which 03's tests invoke.
- Commit once after 04 passes, using
  `feat(cli): auto-manage .gitignore for vendored symlinks (#1)`.
  Solo-repo direct-to-main push convention applies.

## Non-goals (for this PR)

- No `pre-commit` hook installation — issue mentions it as a workaround
  but doesn't request it.
- No rewriting existing `.gitignore` to add `.dotfiles-backup/` or other
  ai-dotfiles tangential paths — only the symlink set.
- No support for managing `.hgignore` / any non-git VCS.
- No `git rm --cached` for paths already tracked pre-install. Issue says
  the future-consumer use case is eliminating the *manual step*, not
  untracking history.
- No change to symlink creation itself (targets, backups, chmod).

## Verification (after all subtasks land)

```bash
poetry run pytest -q
poetry run mypy src/
poetry run ruff check src/ tests/
poetry run black --check src/ tests/
poetry run pre-commit run --all-files

# Manual smoke (from a throwaway git repo)
cd /tmp && rm -rf ignore-smoke && mkdir ignore-smoke && cd ignore-smoke
git init -q
ai-dotfiles init
ai-dotfiles add @<some-existing-domain>
cat .gitignore       # managed block listing /.claude/skills/...
git check-ignore -v .claude/skills/<any-linked-skill>  # matches block
ai-dotfiles remove @<domain>
cat .gitignore       # block shrinks / disappears

# Opt-out
echo '{"packages": [], "manage_gitignore": false}' > ai-dotfiles.json
ai-dotfiles add @<domain>
grep -c 'ai-dotfiles managed' .gitignore  # 0
```

## Files (cumulative)

- `src/ai_dotfiles/core/gitignore.py`          (new, 01)
- `src/ai_dotfiles/commands/add.py`            (02)
- `src/ai_dotfiles/commands/remove.py`         (02)
- `src/ai_dotfiles/commands/install.py`        (02)
- `src/ai_dotfiles/core/manifest.py`           (02 — new helper `get_flag(path, key, default)`)
- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` (04)
- `README.md`                                  (04)
- `tests/unit/test_gitignore.py`               (new, 01)
- `tests/integration/test_gitignore_sync.py`   (new, 03)
- `tests/e2e/test_gitignore_cli.py`            (new, 03)
