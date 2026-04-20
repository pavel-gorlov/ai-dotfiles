# Subtask 02: `ai-dotfiles vendor search <query>` (aggregated)

Depends on subtask 01 being landed on disk (avoids merge conflict on
`commands/vendor.py`).

## Goal

New top-level meta command on the `vendor` group. Queries every
registered vendor that (a) exposes a `search()` method and (b) has all
runtime deps installed. Prints results grouped by vendor.

Command surface:

```
ai-dotfiles vendor search <query>
  -v / --vendor NAME   Restrict to one or more vendors (repeatable).
  -n / --limit  N      Max rows per vendor. Default 20.
```

Output example:

```
=== skills_sh (3 results) ===
NAME                 DESCRIPTION                       INSTALLS   URL
git-workflow                                           124        https://…
…

=== paks (0 results) ===
(no matches)

=== buildwithclaude — skipped (deps missing: git  ->  https://git-scm.com/) ===

=== tonsofskills — error: <message> ===
```

Final fallback line when every vendor yielded zero rows: `No results.`

## File scope (exclusive)

- `src/ai_dotfiles/commands/vendor.py`
- `tests/e2e/test_vendor_meta.py`
- `tests/e2e/test_cli.py`

## Do NOT touch

- Any vendor module under `src/ai_dotfiles/vendors/`
- `src/ai_dotfiles/vendors/base.py` (no shared `SearchResult` yet)
- `_meta_list` in `commands/vendor.py` (already edited by subtask 01 —
  leave alone)
- `README.md`, `ai-dotfiles-blueprint.md`, scaffolded skill (subtask 03)

## Hard rules

- mypy `--strict` clean; `X | None`; no print (`ui.*` + `click.echo` for
  table bodies as elsewhere in this file); absolute imports
- Duck-typing adapter lives in `commands/vendor.py` — do NOT export it,
  do NOT add a shared base class
- Catch broad `Exception` around each `v.search(query)` call and
  convert to `ui.warn(...)` + continue. Do NOT swallow `KeyboardInterrupt`
  / `SystemExit` (narrow the except accordingly)
- Unknown `--vendor` name raises `click.UsageError` (non-zero exit)
- Empty query → `click.UsageError("query must not be empty")`
- Command name `search` — must NOT shadow per-vendor `search` (which is
  attached inside vendor subgroups, different namespace)
- Reuse the existing `_format_table` helper — no new table code

## Implementation sketch

```python
# somewhere near _meta_list / _meta_installed / _meta_remove

def _adapt_hit(hit: object) -> dict[str, str]:
    """Extract display fields from any vendor's SearchResult.
    skills_sh lacks 'description' — defaults to ''."""
    return {
        "name":        str(getattr(hit, "name", "") or ""),
        "description": str(getattr(hit, "description", "") or ""),
        "installs":    str(getattr(hit, "installs", "") or ""),
        "url":         str(getattr(hit, "url", "") or ""),
    }


@click.command(name="search")
@click.argument("query")
@click.option(
    "--vendor", "-v", "restrict",
    multiple=True,
    help="Restrict search to named vendors (repeatable).",
)
@click.option(
    "--limit", "-n",
    type=int, default=20, show_default=True,
    help="Maximum rows per vendor.",
)
def _meta_search(query: str, restrict: tuple[str, ...], limit: int) -> None:
    """Search every active vendor and group results by vendor."""
    if not query.strip():
        raise click.UsageError("query must not be empty")

    unknown = [name for name in restrict if name not in REGISTRY]
    if unknown:
        raise click.UsageError(
            f"unknown vendor(s): {', '.join(unknown)}; "
            f"see 'ai-dotfiles vendor list'"
        )

    targets = [
        (name, v) for name, v in REGISTRY.items()
        if (not restrict or name in restrict)
        and hasattr(v, "search")
    ]

    any_hits = False
    for name, v in targets:
        missing = [d for d in v.deps if not d.is_installed()]
        if missing:
            deps_hint = ", ".join(
                f"{d.name}  ->  {d.install_url}" for d in missing
            )
            ui.info(f"=== {name} — skipped (deps missing: {deps_hint}) ===")
            continue

        try:
            hits = list(v.search(query))[:limit]
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:  # noqa: BLE001 — intentional: vendor failures must not halt aggregate search
            ui.warn(f"=== {name} — error: {exc} ===")
            continue

        ui.info(f"=== {name} ({len(hits)} results) ===")
        if not hits:
            click.echo("(no matches)")
            continue

        any_hits = True
        rows = [
            [a["name"], a["description"], a["installs"], a["url"]]
            for a in (_adapt_hit(h) for h in hits)
        ]
        click.echo(_format_table(
            ["NAME", "DESCRIPTION", "INSTALLS", "URL"], rows
        ))

    if not any_hits:
        ui.info("No results.")


# registration: alongside the other meta commands, before _register_vendors
vendor.add_command(_meta_search)
```

## Test additions

In `tests/e2e/test_vendor_meta.py`:

1. `test_vendor_meta_search_aggregates_across_vendors`
   Monkeypatch `shutil.which` so every dep resolves. Replace each
   vendor's `search` (via `monkeypatch.setattr`) with a stub returning a
   fixed list of its own `SearchResult`. Assert:
   - `=== skills_sh (N results) ===` header.
   - `=== paks (M results) ===` header.
   - `=== buildwithclaude (K results) ===` header.
   - `=== tonsofskills (L results) ===` header.
   - Each stub's URLs appear in output.
   - No `=== github` header (no `search` method).

2. `test_vendor_meta_search_skips_vendors_with_missing_deps`
   Patch `shutil.which` so only `git` is present. Stub `search` on
   `BUILDWITHCLAUDE` / `TONSOFSKILLS`. Assert `skipped (deps missing:
   npx  ->  https://nodejs.org/)` for `skills_sh`, same pattern for
   `paks`, and real result sections for the git-backed vendors.

3. `test_vendor_meta_search_filter_by_vendor`
   `-v paks -v skills_sh`. Only two sections appear. `--vendor github`
   → zero `search`-capable targets, `No results.`.

4. `test_vendor_meta_search_limit_applied`
   Stub `search` to return 50 hits. Invoke with `--limit 3`. Section
   header says `(3 results)`; table has 3 rows.

5. `test_vendor_meta_search_vendor_error_continues`
   Stub one vendor's `search` to `raise RuntimeError("boom")`. Others
   return hits. Assert `=== <name> — error: boom ===` present and other
   sections still rendered. Exit code 0.

6. `test_vendor_meta_search_unknown_vendor_errors`
   `-v nope` → non-zero exit; stderr/click error mentions `nope`.

7. `test_vendor_meta_search_empty_query`
   `vendor search ""` → non-zero exit; error mentions empty query.

8. `test_vendor_meta_search_no_matches_anywhere`
   All stubs return `[]` → `No results.`; exit 0; no `===` section has
   a table body (just headers + `(no matches)` lines).

In `tests/e2e/test_cli.py`:

- Extend the `VENDOR_SUBCOMMANDS` parametrize list (around line 27) to
  include `"search"`. Keep alphabetical order. Add `"paks"`,
  `"buildwithclaude"`, `"tonsofskills"` if they're missing (they should
  already be covered — check first; add only if absent).
- Add `test_help_vendor_search` — invoke `["vendor", "search", "--help"]`
  and assert presence of `--vendor`, `--limit`, and `QUERY` in output.

## Definition of Done

1. `poetry run pytest tests/e2e/test_vendor_meta.py tests/e2e/test_cli.py -q` — all pass
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed; the
   `noqa: BLE001` above is intentional)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. Manual:
   - `poetry run ai-dotfiles vendor search --help` shows the two options
   - `poetry run ai-dotfiles vendor search git` produces grouped output
   - `poetry run ai-dotfiles vendor search git -v buildwithclaude` limits
     scope

Do NOT commit. Orchestrator commits after subtask 03 lands.
