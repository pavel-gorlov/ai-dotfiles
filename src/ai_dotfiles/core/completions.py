"""Data providers for shell tab-completion.

Each ``list_*`` helper scans the catalog or manifests and returns plain
strings that are valid arguments for the corresponding CLI command.
Functions in this module never raise — on any error they return ``[]``, so a
broken catalog or missing manifest cannot take the user's shell down.

The ``make_completer`` factory wraps a data function into a Click
``shell_complete`` callback that filters by the user-typed prefix. Command
modules attach these callbacks via ``shell_complete=...`` on their
``@click.argument(...)`` decorators.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import click

from ai_dotfiles.core import manifest, paths

# Pseudo-dirs directly under ``catalog/`` that hold standalone elements, not
# domains. When listing domains, skip these so tab-completion only shows real
# domains.
_STANDALONE_DIRS: frozenset[str] = frozenset({"skills", "agents", "rules"})
_VALID_ELEMENT_TYPES: frozenset[str] = frozenset({"skill", "agent", "rule"})


# ── Catalog introspection ────────────────────────────────────────────────────


def list_domain_names(include_reserved: bool = False) -> list[str]:
    """Names of domains under ``catalog/``.

    Excludes ``skills/``, ``agents/``, ``rules/`` (standalone pseudo-dirs) and,
    unless ``include_reserved`` is true, reserved names starting with ``_``
    (e.g. ``_example``).
    """
    try:
        catalog = paths.catalog_dir()
        if not catalog.is_dir():
            return []
        names: list[str] = []
        for entry in catalog.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            if name in _STANDALONE_DIRS:
                continue
            if not include_reserved and name.startswith("_"):
                continue
            names.append(name)
        return sorted(names)
    except OSError:
        return []


def list_standalone_elements(element_type: str) -> list[str]:
    """Names of standalone elements of ``element_type`` under ``catalog/``."""
    if element_type not in _VALID_ELEMENT_TYPES:
        return []
    try:
        catalog = paths.catalog_dir()
        if element_type == "skill":
            parent = catalog / "skills"
            if not parent.is_dir():
                return []
            return sorted(e.name for e in parent.iterdir() if e.is_dir())
        parent = catalog / f"{element_type}s"
        if not parent.is_dir():
            return []
        return sorted(
            e.stem for e in parent.iterdir() if e.is_file() and e.suffix == ".md"
        )
    except OSError:
        return []


def list_elements_in_domain(domain: str, element_type: str) -> list[str]:
    """Element names inside ``catalog/<domain>/<element_type>s/``."""
    if element_type not in _VALID_ELEMENT_TYPES:
        return []
    try:
        domain_root = paths.catalog_dir() / domain
        if not domain_root.is_dir():
            return []
        if element_type == "skill":
            parent = domain_root / "skills"
            if not parent.is_dir():
                return []
            return sorted(e.name for e in parent.iterdir() if e.is_dir())
        parent = domain_root / f"{element_type}s"
        if not parent.is_dir():
            return []
        return sorted(
            e.stem for e in parent.iterdir() if e.is_file() and e.suffix == ".md"
        )
    except OSError:
        return []


def list_catalog_specifiers() -> list[str]:
    """All installable specifiers in the catalog.

    Returns domain specifiers (``@name``) and standalone element specifiers
    (``skill:name`` / ``agent:name`` / ``rule:name``).
    """
    specs: list[str] = []
    specs.extend(f"@{name}" for name in list_domain_names())
    for kind in ("skill", "agent", "rule"):
        specs.extend(f"{kind}:{name}" for name in list_standalone_elements(kind))
    return specs


def list_vendored_element_names() -> list[str]:
    """Names of catalog entries that came from a vendor (have ``.source``)."""
    try:
        catalog = paths.catalog_dir()
        if not catalog.is_dir():
            return []
        names: set[str] = set()
        for kind in ("skill", "agent", "rule"):
            parent = catalog / f"{kind}s"
            if not parent.is_dir():
                continue
            for entry in parent.iterdir():
                if entry.is_dir() and (entry / ".source").is_file():
                    names.add(entry.name)
        return sorted(names)
    except OSError:
        return []


# ── Manifests ────────────────────────────────────────────────────────────────


def _project_manifest() -> Path | None:
    root = paths.find_project_root()
    if root is None:
        return None
    candidate = paths.project_manifest_path(root)
    return candidate if candidate.is_file() else None


def list_installed_specifiers(is_global: bool) -> list[str]:
    """Specifiers present in the manifest for the chosen scope.

    When ``is_global`` is True, reads ``~/.ai-dotfiles/global.json``. Otherwise
    reads the project manifest discovered via :func:`paths.find_project_root`.
    Returns ``[]`` if the manifest does not exist or cannot be parsed.
    """
    try:
        if is_global:
            manifest_path = paths.global_manifest_path()
            if not manifest_path.is_file():
                return []
        else:
            manifest_path = _project_manifest()  # type: ignore[assignment]
            if manifest_path is None:
                return []
        return list(manifest.get_packages(manifest_path))
    except Exception:
        return []


def list_available_specifiers(is_global: bool) -> list[str]:
    """Catalog specifiers NOT already installed in the given scope.

    Installed specifiers are appended at the end (suffixed) so users see both
    fresh and already-linked items, with fresh ones ordered first.
    """
    catalog = list_catalog_specifiers()
    installed = set(list_installed_specifiers(is_global))
    fresh = [s for s in catalog if s not in installed]
    already = [s for s in catalog if s in installed]
    return fresh + already


# ── Click callback wiring ────────────────────────────────────────────────────


Completer = Callable[[click.Context, click.Parameter, str], list[str]]


def make_completer(
    fn: Callable[[click.Context], Iterable[str]],
) -> Completer:
    """Wrap ``fn(ctx) -> items`` into a Click ``shell_complete`` callback.

    Filters items by ``incomplete`` prefix and swallows any exception so a
    misbehaving provider never breaks the user's shell.
    """

    def _complete(
        ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> list[str]:
        try:
            items = list(fn(ctx))
        except Exception:
            return []
        return [item for item in items if item.startswith(incomplete)]

    return _complete


def _scope_from_ctx(ctx: click.Context) -> bool:
    """Extract the ``is_global`` flag from the current command's parsed params."""
    return bool(ctx.params.get("is_global", False))


# Pre-built completers for common shapes.


def complete_available_specifiers(ctx: click.Context) -> list[str]:
    """For ``add``: prefer not-yet-installed, append already-installed."""
    return list_available_specifiers(_scope_from_ctx(ctx))


def complete_installed_specifiers(ctx: click.Context) -> list[str]:
    """For ``remove``: only specifiers currently in the manifest."""
    return list_installed_specifiers(_scope_from_ctx(ctx))


def complete_domain_names(ctx: click.Context) -> list[str]:
    """For ``domain <subcommand> <name>``: existing domain names."""
    return list_domain_names()


def complete_domain_elements(ctx: click.Context) -> list[str]:
    """For ``domain remove <name> <type> <el>``: elements of ``type`` in ``name``."""
    name = ctx.params.get("name")
    element_type = ctx.params.get("element_type")
    if not isinstance(name, str) or not isinstance(element_type, str):
        return []
    return list_elements_in_domain(name, element_type)


def complete_standalone_elements(ctx: click.Context) -> list[str]:
    """For ``delete skill|agent|rule <name>``: existing standalone elements."""
    element_type = ctx.params.get("element_type")
    if not isinstance(element_type, str):
        return []
    return list_standalone_elements(element_type)


def complete_vendored_names(ctx: click.Context) -> list[str]:
    """For ``vendor remove <name>``: names with ``.source`` sidecars."""
    return list_vendored_element_names()
