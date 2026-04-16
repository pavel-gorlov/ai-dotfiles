# Vendor P0: refactor `Dependency` + drop `deps install`

Simplify the vendor-dependency data model and remove the auto-installer
subcommand. Going forward, `deps check` tells the user what's missing
and points at the upstream install URL — nothing is installed by
ai-dotfiles.

## Goal

- Replace `Dependency(name, check, install_cmd, manual_hint)` with
  `Dependency(name, check, install_url)` everywhere.
- Delete the `vendor <v> deps install` click command and the
  `vendors.deps.install()` function (+ tests).
- `vendor <v> deps check` prints `<name>: + installed` for present
  deps and `<name>: x missing  ->  <install_url>` for missing ones;
  exits 1 if any missing, 0 otherwise.

## File scope

**Edit** (exclusive to this task):

- `src/ai_dotfiles/vendors/base.py` — new `Dependency` dataclass
- `src/ai_dotfiles/vendors/deps.py` — remove `install()`; keep
  `check()` and `ensure()`; update error messages to include
  `install_url`
- `src/ai_dotfiles/vendors/github.py` — update its `Dependency` instance
- `src/ai_dotfiles/vendors/skills_sh.py` — update its `Dependency`
- `src/ai_dotfiles/commands/vendor.py` — remove the `install`
  subcommand from `_make_deps_group`; rewrite `_deps_check` to print
  install URLs for missing deps
- `tests/unit/test_deps.py` — rewrite for the new schema; remove all
  `install()` tests
- `tests/e2e/test_vendor_meta.py` — remove any `vendor <v> deps
  install` tests; update `deps check missing` tests to assert URL in
  output
- `tests/e2e/test_cli.py` — update `VENDOR_DEPS_SUBCOMMANDS` (remove
  `"install"`)

**Do NOT touch**: `source_file.py`, `placement.py`, README or blueprint
(P2 updates docs once paks lands), other test files, CI config.

## Hard rules

- mypy `--strict` clean; `X | None` syntax; no print; absolute imports
- `Dependency` stays a frozen dataclass
- `deps.ensure` still raises `ExternalError` when deps missing; error
  message format: `"missing dependency '<name>'; install: <url>"`
- `install_url` must be a non-empty string (validate in `__post_init__`
  or rely on call-site discipline — keep simple, no validation if
  callers are trusted)
- Do NOT leave dead imports or dead code

## Install URLs for existing vendors

- git → `https://git-scm.com/`
- npx → `https://nodejs.org/`

## Definition of Done

1. `poetry run pytest -q` — full suite green
2. `poetry run mypy src/` — clean
3. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
4. `poetry run black --check src/ tests/` — clean
5. `poetry run pre-commit run --all-files` — clean
6. Manual: `poetry run ai-dotfiles vendor skills_sh deps --help`
   shows only `check` (no `install`)
7. Manual: `poetry run ai-dotfiles vendor skills_sh deps check` prints
   `npx: + installed` on a machine with npx, or
   `npx: x missing  ->  https://nodejs.org/` without

Do NOT commit. Report files, gate outputs, deviations.
