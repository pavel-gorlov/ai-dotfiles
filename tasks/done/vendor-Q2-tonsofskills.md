# Vendor Q2: `tonsofskills` vendor

Add a vendor backed by
https://github.com/jeremylongshore/claude-code-plugins-plus-skills
(MIT, 340 plugins + 1367 skills — the catalog behind CCPI). Use the
same `_repo_cache` infrastructure from Q0 and the same surface as
`buildwithclaude` from Q1.

## File scope

- `src/ai_dotfiles/vendors/tonsofskills.py` (new)
- `tests/e2e/test_vendor_tonsofskills.py` (new)
- `src/ai_dotfiles/vendors/__init__.py` — register `TONSOFSKILLS` in
  REGISTRY and `__all__`

## Do NOT touch

- Other vendor modules (`paks`, `skills_sh`, `github`, `buildwithclaude`)
- `_repo_cache.py`
- `commands/vendor.py`
- README / blueprint

## Real-layout probe (first step)

```bash
TMP=$(mktemp -d)
git clone --depth=1 \
  https://github.com/jeremylongshore/claude-code-plugins-plus-skills.git \
  "$TMP/ts"
find "$TMP/ts" -name SKILL.md | head -20
ls "$TMP/ts/.claude-plugin" 2>/dev/null || true
tree -L 3 "$TMP/ts" 2>/dev/null | head -80 || ls -la "$TMP/ts"
rm -rf "$TMP"
```

Document observed layout in the module docstring.

## Module shape

Mirror `buildwithclaude.py`:

```python
_REPO_URL = (
    "https://github.com/jeremylongshore/claude-code-plugins-plus-skills.git"
)


@dataclass(frozen=True)
class _TonsOfSkillsVendor:
    name: str = "tonsofskills"
    display_name: str = "tonsofskills"
    description: str = "Install skills from the tonsofskills.com catalog."
    deps: tuple[Dependency, ...] = (_GIT_DEPENDENCY,)

    def list_source(self, source: str) -> Iterable[str]: ...
    def search(self, query: str) -> list[SearchResult]: ...
    def fetch(self, source, *, select, workdir) -> list[FetchedItem]: ...
    def refresh(self, *, force: bool = False) -> Path: ...
```

Methods behave identically to `buildwithclaude`'s versions — only the
repo URL differs. Origin prefix: `tonsofskills:<name>`. URL template:
`https://github.com/jeremylongshore/claude-code-plugins-plus-skills/tree/main/<relpath>`.

**If Q1 and Q2 agents end up duplicating large helper blocks**, leave
them duplicated — a follow-up refactor can lift them into a shared
`_marketplace.py` base. Do NOT introduce the shared base preemptively
(each vendor remains self-contained, matching the existing pattern).

## Registration

Append to `vendors/__init__.py` in the same commit that Q1 lands in?
No — Q1 and Q2 run in parallel, and both edit `__init__.py`.
**Coordination**:

- Q1 adds its import + REGISTRY entry + `__all__` entry for
  `BUILDWITHCLAUDE`.
- Q2 adds its import + REGISTRY entry + `__all__` entry for
  `TONSOFSKILLS`.

If both land cleanly the file will have both entries. Orchestrator
resolves any merge conflict before committing.

## Tests

Same cases as Q1, adapted:

1. `list_source` returns singleton
2. `search` happy path with 3 fake SKILL.md in a temp cache
3. `search` matches description
4. `search` matches tags
5. `search` empty query → ValueError
6. `search` no matches → ExternalError
7. `refresh(force=True)` delegates correctly
8. `fetch` copies matching dir into `workdir/out/`
9. `fetch` `--select` rejected
10. `fetch` unknown source → ExternalError
11. License detection
12. Registry membership
13. Deps
14. Metadata

Mock `_repo_cache.refresh` and pre-populate fake layout on `tmp_path`.

## Hard rules

- mypy --strict; `X | None`; no print; absolute imports
- Self-contained module; copy helpers where needed
- No real git ops in tests

## DoD

1. `poetry run pytest tests/e2e/test_vendor_tonsofskills.py -q` — all pass
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. Manual: `poetry run ai-dotfiles vendor tonsofskills --help` lists
   `install`, `list`, `search`, `refresh`, `deps`

Do NOT commit. Report files, gate outputs, empirical layout findings
(Q3 docs depend on this), deviations.
