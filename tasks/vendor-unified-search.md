# Feature: unified vendor search + install-URLs in `vendor list`

## Goal

Ship two CLI additions against the existing vendor subsystem:

1. **`ai-dotfiles vendor search <query>`** — top-level meta command that
   runs `search` on every active vendor (has `search()` AND all deps
   installed) and prints results grouped by vendor.
2. **`ai-dotfiles vendor list`** — extend existing output so missing deps
   show their install URL inline: `npx: x -> https://nodejs.org/`.

## Why

Currently users have to run `vendor <plugin> search <query>` once per
vendor and run `deps check` per vendor to find install URLs. This stitches
the experience together.

## Plan

Three subtasks, run sequentially to avoid conflicts on
`commands/vendor.py`:

| # | Subtask | Details |
|---|---------|---------|
| 1 | `vendor list` install URLs  | [vendor-unified-search/01-list-install-urls.md](vendor-unified-search/01-list-install-urls.md) |
| 2 | `vendor search <query>`     | [vendor-unified-search/02-search-command.md](vendor-unified-search/02-search-command.md) |
| 3 | Docs + scaffolded skill     | [vendor-unified-search/03-docs.md](vendor-unified-search/03-docs.md) |

### Execution

```
01 (list install URLs)
   │
   v
02 (search command)   <- depends on file state from 01
   │
   v
03 (docs)             <- depends on final CLI surface
```

Each subtask ends on its own DoD gates (mypy, ruff, black, pytest,
pre-commit). Orchestrator only commits once all three pass.

## Orchestrator role

- Dispatch subtasks in order (01 → 02 → 03).
- After each subtask: run `poetry run pytest -q`, `poetry run mypy src/`,
  `poetry run ruff check src/ tests/`, `poetry run black --check
  src/ tests/`, `poetry run pre-commit run --all-files`. Halt on failure
  and report to user.
- Never run subtasks in parallel — all three touch `commands/vendor.py`
  or its adjacent tests.
- Do NOT ask the subagents to commit. Commit once after 03 lands and all
  gates pass, using a single `feat(vendor): unified search + install URLs
  in list` message.

## Non-goals

- No parallel/async search — sequential iteration across vendors.
- No `--json` output.
- No shared `SearchResult` base class in `vendors/base.py`. Vendor
  modules are untouched; schema variation is absorbed by a duck-typing
  adapter at the CLI layer.
- No cross-vendor dedup, ranking, or pagination.
- No new third-party deps.

## Verification (after all subtasks land)

```bash
poetry run pytest -q
poetry run mypy src/
poetry run ruff check src/ tests/
poetry run black --check src/ tests/
poetry run pre-commit run --all-files

# manual smoke
poetry run ai-dotfiles vendor list
poetry run ai-dotfiles vendor search --help
poetry run ai-dotfiles vendor search git
poetry run ai-dotfiles vendor search git -v buildwithclaude
poetry run ai-dotfiles vendor search git --limit 3
```

## Files touched (cumulative)

- `src/ai_dotfiles/commands/vendor.py`
- `tests/e2e/test_vendor_meta.py`
- `tests/e2e/test_cli.py`
- `README.md`
- `ai-dotfiles-blueprint.md`
- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
