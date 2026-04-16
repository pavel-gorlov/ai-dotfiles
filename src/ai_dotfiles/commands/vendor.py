"""``ai-dotfiles vendor`` — manage external content fetched by vendor plugins.

Structure
---------

``vendor`` is a :class:`click.Group` with:

* Meta subcommands operating across all vendors:

    * ``list`` — show the registry (vendors + deps status)
    * ``installed`` — list ``.source`` entries found under ``catalog/``
    * ``remove`` — delete a catalog entry (any kind) by name

* Per-vendor subgroups built dynamically from
  :data:`ai_dotfiles.vendors.REGISTRY`. For each vendor the group
  exposes ``install``, ``list`` (source contents) and a ``deps``
  subgroup with ``check``.

All logic is delegated to :mod:`ai_dotfiles.vendors` and
:mod:`ai_dotfiles.core`; this module is intentionally a thin CLI
adapter that parses arguments, formats output, and maps
:class:`AiDotfilesError` subclasses to exit codes.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.commands.create_delete import find_usage
from ai_dotfiles.core.errors import AiDotfilesError, ElementError
from ai_dotfiles.core.paths import catalog_dir, find_project_root, storage_root
from ai_dotfiles.vendors import REGISTRY, source_file
from ai_dotfiles.vendors import deps as deps_mod
from ai_dotfiles.vendors.base import SourceMeta, Vendor
from ai_dotfiles.vendors.placement import place_item

_VALID_KINDS: tuple[str, ...] = ("skill", "agent", "rule")


def _parse_select(raw: str | None) -> tuple[str, ...] | None:
    """Parse ``--select "a, b, c"`` into ``("a", "b", "c")``.

    Whitespace around entries is trimmed; empty entries (``"a,,b"``)
    raise :class:`ElementError`. Returns ``None`` if ``raw`` is ``None``
    or an empty/blank string.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    parts = [p.strip() for p in stripped.split(",")]
    if any(not p for p in parts):
        raise ElementError(
            "--select contains an empty entry; expected a comma-separated list "
            "of non-empty names."
        )
    return tuple(parts)


def _iter_catalog_sources(
    catalog: Path,
) -> list[tuple[Path, str, str, SourceMeta]]:
    """Return ``(item_dir, kind, name, meta)`` for every ``.source`` found.

    Walks ``catalog/<kinds>/<name>/`` directories and reads
    ``.source`` files. Skips directories without a ``.source`` file.
    """
    rows: list[tuple[Path, str, str, SourceMeta]] = []
    if not catalog.is_dir():
        return rows
    for kind in _VALID_KINDS:
        kind_dir = catalog / f"{kind}s"
        if not kind_dir.is_dir():
            continue
        for entry in sorted(kind_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta = source_file.read(entry)
            if meta is None:
                continue
            rows.append((entry, kind, entry.name, meta))
    return rows


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Return a simple two-space-separated fixed-width table as a string."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > widths[i]:
                widths[i] = len(cell)
    lines: list[str] = []
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line.rstrip())
    for row in rows:
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line.rstrip())
    return "\n".join(lines)


# ── Meta commands ────────────────────────────────────────────────────────────


@click.command(name="list")
def _meta_list() -> None:
    """List registered vendors and their dependency status."""
    try:
        rows: list[list[str]] = []
        for name, vendor in REGISTRY.items():
            dep_cells = [
                f"{d.name}: {'+' if d.is_installed() else 'x'}" for d in vendor.deps
            ]
            rows.append([name, vendor.description, ", ".join(dep_cells)])
        ui.info(_format_table(["NAME", "DESCRIPTION", "DEPS"], rows))
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@click.command(name="installed")
def _meta_installed() -> None:
    """List every vendored item found under ``catalog/``."""
    try:
        catalog = catalog_dir()
        rows_meta = _iter_catalog_sources(catalog)
        if not rows_meta:
            ui.info("No vendored items.")
            return
        # Sort by kind then name.
        rows_meta.sort(key=lambda r: (r[1], r[2]))
        rows: list[list[str]] = []
        for _item_dir, kind, name, meta in rows_meta:
            rows.append([name, kind, meta.vendor, meta.origin, meta.fetched])
        ui.info(
            _format_table(
                ["NAME", "KIND", "VENDOR", "ORIGIN", "FETCHED"],
                rows,
            )
        )
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@click.command(name="remove")
@click.argument("name")
@click.option(
    "--kind",
    type=click.Choice(list(_VALID_KINDS)),
    default=None,
    help="Narrow the search when a name exists in multiple kinds.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip the confirmation prompt.",
)
def _meta_remove(name: str, kind: str | None, yes: bool) -> None:
    """Remove a vendored entry named NAME from ``catalog/``."""
    try:
        catalog = catalog_dir()
        matches: list[tuple[Path, str]] = []
        kinds_to_check: tuple[str, ...] = (kind,) if kind is not None else _VALID_KINDS
        for k in kinds_to_check:
            candidate = catalog / f"{k}s" / name
            if candidate.is_dir() and (candidate / ".source").exists():
                matches.append((candidate, k))

        if not matches:
            where = f"{kind}s/" if kind is not None else "catalog/"
            raise ElementError(f"No vendored item named '{name}' found under {where}.")
        if len(matches) > 1:
            kinds_found = ", ".join(m[1] for m in matches)
            raise ElementError(
                f"Ambiguous: '{name}' is vendored under multiple kinds "
                f"({kinds_found}). Re-run with --kind <skill|agent|rule>."
            )

        target, target_kind = matches[0]

        element_raw = f"{target_kind}:{name}"
        usages = find_usage(element_raw, storage_root(), find_project_root())
        if usages:
            ui.warn(f"{element_raw} is used in: {', '.join(usages)}")

        if not yes and not ui.confirm(f"Remove {element_raw}?", default=False):
            ui.info("Aborted.")
            return

        shutil.rmtree(target)
        try:
            rel = target.relative_to(storage_root())
            ui.success(f"Removed {rel}/")
        except ValueError:
            ui.success(f"Removed {target}/")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


# ── Per-vendor command factories ─────────────────────────────────────────────


def _make_install_command(vendor: Vendor) -> click.Command:
    """Build the ``install`` subcommand bound to ``vendor``."""

    @click.command(
        name="install", help=f"Install content via the '{vendor.name}' vendor."
    )
    @click.argument("source")
    @click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Overwrite existing catalog entries.",
    )
    @click.option(
        "--select",
        "select_raw",
        type=str,
        default=None,
        help="Comma-separated subset of items to install (vendor-dependent).",
    )
    def _install(source: str, force: bool, select_raw: str | None) -> None:
        try:
            select = _parse_select(select_raw)
            deps_mod.ensure(vendor)

            catalog = catalog_dir()
            catalog.mkdir(parents=True, exist_ok=True)

            placed: list[tuple[str, str]] = []
            with tempfile.TemporaryDirectory() as work:
                workdir = Path(work)
                items = vendor.fetch(source, select=select, workdir=workdir)
                for item in items:
                    place_item(
                        item,
                        catalog_root=catalog,
                        force=force,
                        vendor_name=vendor.name,
                    )
                    placed.append((item.kind, item.name))

            for kind, name in placed:
                ui.success(f"Installed catalog/{kind}s/{name}/")

            if placed:
                ui.info("")
                ui.info("Ready to use:")
                for kind, name in placed:
                    ui.info(f"  ai-dotfiles add {kind}:{name}")
        except AiDotfilesError as exc:
            ui.error(str(exc))
            sys.exit(exc.exit_code)

    return _install


def _make_list_source_command(vendor: Vendor) -> click.Command:
    """Build the ``list`` (source) subcommand bound to ``vendor``."""

    @click.command(
        name="list",
        help=f"List items exposed by a source for the '{vendor.name}' vendor.",
    )
    @click.argument("source")
    def _list_source(source: str) -> None:
        try:
            deps_mod.ensure(vendor)
            for name in vendor.list_source(source):
                click.echo(name)
        except AiDotfilesError as exc:
            ui.error(str(exc))
            sys.exit(exc.exit_code)

    return _list_source


def _make_search_command(vendor: Vendor) -> click.Command | None:
    """Build the ``search`` subcommand for vendors that implement it.

    Returns ``None`` for vendors without a ``search`` method — only
    ``skills_sh`` exposes one today. Each hit is printed as
    ``<source>@<name>  [<installs>]`` followed by the marketplace URL
    indented beneath it.
    """
    search_method = getattr(vendor, "search", None)
    if search_method is None:
        return None

    @click.command(
        name="search",
        help=f"Search for skills via '{vendor.name}' marketplace.",
    )
    @click.argument("query")
    def _search(query: str) -> None:
        try:
            deps_mod.ensure(vendor)
            results = search_method(query)
        except AiDotfilesError as exc:
            ui.error(str(exc))
            sys.exit(exc.exit_code)

        for hit in results:
            head = f"{hit.source}@{hit.name}"
            if hit.installs:
                head = f"{head}  ({hit.installs} installs)"
            click.echo(head)
            if hit.url:
                click.echo(f"  {hit.url}")

    return _search


def _make_deps_group(vendor: Vendor) -> click.Group:
    """Build the ``deps`` subgroup (``check``) for ``vendor``."""

    @click.group(name="deps", help=f"Manage '{vendor.name}' vendor dependencies.")
    def _deps_group() -> None:
        """Manage vendor runtime dependencies."""

    @click.command(name="check")
    def _deps_check() -> None:
        """Report dependency status; exit 1 if any are missing."""
        any_missing = False
        for dep in vendor.deps:
            if dep.is_installed():
                click.echo(f"{dep.name}: + installed")
            else:
                click.echo(f"{dep.name}: x missing  ->  {dep.install_url}")
                any_missing = True
        sys.exit(1 if any_missing else 0)

    _deps_group.add_command(_deps_check)
    return _deps_group


# ── Group wiring ─────────────────────────────────────────────────────────────


@click.group(name="vendor")
def vendor() -> None:
    """Manage external content fetched by vendor plugins."""


vendor.add_command(_meta_list)
vendor.add_command(_meta_installed)
vendor.add_command(_meta_remove)


def _register_vendors(parent: click.Group) -> None:
    """Build per-vendor subgroups from :data:`REGISTRY` and attach them."""
    for name, v in REGISTRY.items():
        vendor_group = click.Group(name=name, help=v.description)
        vendor_group.add_command(_make_install_command(v))
        vendor_group.add_command(_make_list_source_command(v))
        vendor_group.add_command(_make_deps_group(v))
        search_cmd = _make_search_command(v)
        if search_cmd is not None:
            vendor_group.add_command(search_cmd)
        parent.add_command(vendor_group)


_register_vendors(vendor)
