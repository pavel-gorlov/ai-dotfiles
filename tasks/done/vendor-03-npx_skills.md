# Vendor V3: npx_skills vendor

Add a new vendor that wraps the `npx skills add` CLI (vercel-labs/skills)
and delivers `FetchedItem`s ready for placement.

## Goal

`vendors/npx_skills.py` exposes `NPX_SKILLS: Vendor` with:
- `name = "npx_skills"`
- `display_name = "npx skills"`
- `description = "Install Claude Code skills via the 'skills' npm CLI."`
- `deps = (Dependency(name="npx", ...),)`
- `list_source(source)` — runs `npx -y skills add <source> --list`, parses
  stdout lines into skill names
- `fetch(source, *, select, workdir)` — runs
  `npx -y skills add <source> --copy -y [-s s1 s2 ...]` inside a fresh
  tmp HOME located under `workdir`, then enumerates
  `workdir/<tmp_home>/.claude/skills/*/` and produces one `FetchedItem`
  per directory

## Invocation details

- The upstream CLI has no output-path flag; we redirect its
  `~/.claude/skills/` target by setting `HOME=<workdir/tmp_home>` in the
  subprocess env (pass `env={"HOME": str(home), "PATH": os.environ["PATH"]}`
  plus `"NODE_OPTIONS"` if present)
- Always pass `--copy` and `-y` (prevents symlinks + interactive prompts)
- If `select` is non-empty, pass `-s name1 name2 ...`
- Exit code non-zero → `ExternalError("npx skills add failed: <stderr>")`

## File scope (exclusive)

- `src/ai_dotfiles/vendors/npx_skills.py` (new)
- `tests/e2e/test_vendor_npx_skills.py` (new) — all tests mock
  `subprocess.run` and fake the target directory layout via
  `monkeypatch.setattr`

## Do NOT touch

- `vendors/github.py`, `vendors/base.py`, `source_file.py`, `placement.py`,
  `deps.py`
- `commands/vendor.py` (V4 rewires)
- `vendors/__init__.py` — REGISTRY wiring happens in V4

## Hard rules

- mypy --strict, `X | None`, no print, absolute imports
- Raise `ExternalError` on subprocess failure or parsing errors
- Use `tempfile.TemporaryDirectory()` for the tmp HOME within `workdir`
  (or just `workdir` itself if it's guaranteed empty — simplest: put the
  tmp HOME at `workdir/_npx_home`)
- License detection: read LICENSE files from each resulting skill dir
  (same semantics as `vendors/github.py`)

## Upstream list parsing

`npx skills add <source> --list` output format (observed):
```
Found skills in <source>:
- skill-one
- skill-two
- skill-three
```

Parser: after the header line, take each line starting with `- ` (dash
space), strip. Ignore blank lines. Reject if no skills parsed
(ExternalError).

If the format is different when we actually run it, the parser should
tolerate common variants: lines containing only alphanumerics/hyphens/
underscores in bullet form. Be permissive.

## Acceptance tests (in `test_vendor_npx_skills.py`)

Mock `subprocess.run` to return canned stdout/stderr and simulate file
creation under the tmp HOME. All tests rely on `NPX_SKILLS.fetch(...)`
or `NPX_SKILLS.list_source(...)`:

1. `list_source("vercel-labs/skills")` returns parsed skill names
2. `list_source` on empty output → ExternalError
3. `fetch` happy path: two skills appear, two `FetchedItem`s returned,
   each with kind="skill", correct name, origin, source_dir exists
4. `fetch` with `select=("one","two")` passes `-s one two` to subprocess
5. `fetch` where subprocess exits non-zero → ExternalError with stderr
6. `fetch` where subprocess succeeds but produces no dirs → ExternalError
7. `deps` tuple has `npx` entry; `is_installed()` monkeypatched via
   `shutil.which`
8. License detection: create `LICENSE` in the mocked skill dir; assert
   `item.license` contains its first line (truncated)

## Definition of Done

1. `poetry run pytest tests/e2e/test_vendor_npx_skills.py -q` — all pass
2. Full suite: `poetry run pytest -q` — green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit.
