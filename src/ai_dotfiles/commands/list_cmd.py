"""``ai-dotfiles list`` — show installed packages or catalog contents.

Three modes:

* ``ai-dotfiles list``               — packages from project ``ai-dotfiles.json``
* ``ai-dotfiles list -g``            — packages from ``~/.ai-dotfiles/global.json``
* ``ai-dotfiles list --available``   — everything present in ``catalog/``
  and ``stacks/`` under the storage root
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import manifest, paths
from ai_dotfiles.core.elements import Element, ElementType, parse_element
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError

# Catalog top-level directories that are not standalone domains.
_RESERVED_CATALOG_DIRS: frozenset[str] = frozenset(
    {"skills", "agents", "rules", "_example"}
)


@click.command("list")
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="List packages from the global manifest.",
)
@click.option(
    "--available",
    is_flag=True,
    help="Show all items available in the catalog and stacks.",
)
def list_cmd(is_global: bool, available: bool) -> None:
    """List installed packages, or everything available in the catalog."""
    try:
        if available:
            _list_available()
        elif is_global:
            _list_manifest(paths.global_manifest_path())
        else:
            _list_project()
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


# ── Manifest listing ─────────────────────────────────────────────────────


def _list_project() -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")
    _list_manifest(paths.project_manifest_path(root))


def _list_manifest(manifest_path: Path) -> None:
    packages = manifest.get_packages(manifest_path)
    ui.info(f"Packages ({manifest_path.name}):")
    ui.info("")
    if not packages:
        ui.info("No packages installed.")
        return

    grouped = _group_packages(packages)
    _print_groups(grouped)


def _group_packages(packages: list[str]) -> dict[ElementType, list[str]]:
    grouped: dict[ElementType, list[str]] = {
        ElementType.DOMAIN: [],
        ElementType.SKILL: [],
        ElementType.AGENT: [],
        ElementType.RULE: [],
    }
    for raw in packages:
        element: Element = parse_element(raw)
        grouped[element.type].append(raw)
    return grouped


def _print_groups(grouped: dict[ElementType, list[str]]) -> None:
    sections: list[tuple[str, list[str]]] = [
        ("Domains", grouped[ElementType.DOMAIN]),
        ("Skills", grouped[ElementType.SKILL]),
        ("Agents", grouped[ElementType.AGENT]),
        ("Rules", grouped[ElementType.RULE]),
    ]
    first = True
    for title, items in sections:
        if not items:
            continue
        if not first:
            ui.info("")
        first = False
        ui.info(f"  {title}:")
        for item in items:
            ui.info(f"    {item}")


# ── Available listing ────────────────────────────────────────────────────


def _list_available() -> None:
    catalog = paths.catalog_dir()
    stacks = paths.stacks_dir()

    domains = _scan_domains(catalog)
    skills = _scan_standalone_dirs(catalog / "skills", prefix="skill:")
    agents = _scan_standalone_files(catalog / "agents", prefix="agent:")
    rules = _scan_standalone_files(catalog / "rules", prefix="rule:")
    stack_names = _scan_stacks(stacks)

    ui.info("Available in catalog:")
    ui.info("")

    sections: list[tuple[str, list[str]]] = [
        ("Domains", domains),
        ("Skills", skills),
        ("Agents", agents),
        ("Rules", rules),
    ]
    first = True
    for title, items in sections:
        if not items:
            continue
        if not first:
            ui.info("")
        first = False
        ui.info(f"  {title}:")
        for item in items:
            ui.info(f"    {item}")

    if stack_names:
        ui.info("")
        ui.info("Stacks:")
        for name in stack_names:
            ui.info(f"    {name}")


def _scan_domains(catalog: Path) -> list[str]:
    if not catalog.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(catalog.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name in _RESERVED_CATALOG_DIRS:
            continue
        if entry.name.startswith("_"):
            continue
        names.append(f"@{entry.name}")
    return names


def _scan_standalone_dirs(root: Path, *, prefix: str) -> list[str]:
    if not root.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        names.append(f"{prefix}{entry.name}")
    return names


def _scan_standalone_files(root: Path, *, prefix: str) -> list[str]:
    if not root.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".md":
            continue
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        names.append(f"{prefix}{entry.stem}")
    return names


def _scan_stacks(stacks: Path) -> list[str]:
    if not stacks.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(stacks.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".conf":
            continue
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        names.append(entry.stem)
    return names
