# Vendor P1: rename `find` → `search`

Mechanical rename across code, tests, and docs. Matches upstream
`paks search` and `npx skills find`/`skills find` verbs. No behaviour
change; only identifiers and command names.

## File scope

- `src/ai_dotfiles/vendors/skills_sh.py`
  - method `find(query)` → `search(query)`
  - helper `_parse_find_output` → `_parse_search_output`
  - regex `_FIND_RESULT_RE` → `_SEARCH_RESULT_RE`
  - dataclass `FindResult` → `SearchResult` (same fields)
  - `__all__` entry updated
  - docstrings / comments rephrased
- `src/ai_dotfiles/commands/vendor.py`
  - `_make_find_command` → `_make_search_command`
  - click command `name="search"`, help string updated
  - loop in `_register_vendors` updated
- `tests/e2e/test_vendor_skills_sh.py`
  - imports (`FindResult` → `SearchResult`)
  - test function names `test_find_*` → `test_search_*`
  - test fixture variable names if they contain `find`
- `tests/e2e/test_vendor_meta.py`
  - test function names (`test_vendor_skills_sh_find_*` →
    `..._search_*`)
  - test function `test_vendor_github_has_no_find_subcommand` →
    `..._no_search_subcommand`
  - asserts comparing `" find "` in help output → `" search "`
- `tests/e2e/test_cli.py` — if any VENDOR_*_SUBCOMMANDS list contains
  `"find"`, replace with `"search"`
- `README.md` — update command table row and example block
- `ai-dotfiles-blueprint.md` — update any mention of `find`

Keep the documented capability in the exact same spot in each file;
don't reorganize.

## Do NOT touch

- Task spec files under `tasks/`
- `vendors/base.py`, `deps.py`, `placement.py`, `source_file.py`,
  `github.py`, `__init__.py` — they contain no `find` references
- Core modules

## Hard rules

- mypy `--strict` clean; `X | None`; no print; absolute imports
- No alias or migration shim for `find` — hard break
- All docstrings mentioning "find" should read "search"
- Preserve all test cases — rename only; don't drop or add tests

## Definition of Done

1. `poetry run pytest -q` — full suite green
2. `poetry run mypy src/` — clean
3. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
4. `poetry run black --check src/ tests/` — clean
5. `poetry run pre-commit run --all-files` — clean
6. `poetry run ai-dotfiles vendor skills_sh search --help` works
7. `poetry run ai-dotfiles vendor skills_sh find --help` → "No such
   command"
8. `grep -R 'find' src/ai_dotfiles | grep -v '__pycache__'` — only
   matches should be in comments referring to the file-finding utility
   (if any such exist) or none at all for this vendor area

Do NOT commit. Report files, gate outputs, deviations.
