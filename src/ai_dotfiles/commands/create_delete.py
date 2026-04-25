"""``ai-dotfiles create`` and ``ai-dotfiles delete`` — manage standalone elements.

Both commands operate on the *catalog* (``<storage>/catalog/``) for standalone
elements (not inside any domain):

* ``skill`` — ``catalog/skills/<name>/`` directory with a generated
  ``SKILL.md``
* ``agent`` — ``catalog/agents/<name>.md`` file
* ``rule``  — ``catalog/rules/<name>.md`` file

``delete`` additionally scans manifests (project ``ai-dotfiles.json``,
``global.json``) and every ``stacks/*.conf`` file so it can warn the user when
they're about to remove something still referenced elsewhere.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core.completions import (
    complete_standalone_elements,
    make_completer,
)
from ai_dotfiles.core.elements import parse_element
from ai_dotfiles.core.errors import AiDotfilesError, ElementError
from ai_dotfiles.core.manifest import get_packages
from ai_dotfiles.core.paths import (
    catalog_dir,
    find_project_root,
    project_manifest_path,
    storage_root,
)
from ai_dotfiles.scaffold.generator import generate_element_from_template

_VALID_TYPES: tuple[str, ...] = ("skill", "agent", "rule")


def _element_path(element_type: str, name: str, catalog: Path) -> Path:
    """Return the on-disk path for a standalone element in ``catalog/``."""
    if element_type == "skill":
        return catalog / "skills" / name
    if element_type == "agent":
        return catalog / "agents" / f"{name}.md"
    if element_type == "rule":
        return catalog / "rules" / f"{name}.md"
    raise ElementError(f"Unknown element type: {element_type!r}")


def find_usage(
    element_raw: str,
    storage: Path,
    project_root: Path | None,
) -> list[str]:
    """Find where ``element_raw`` (e.g. ``skill:my-linter``) is referenced.

    Scans the current project manifest (if any) and the global manifest.
    Returns a list of string paths (relative to their natural base) in
    which the element appears.
    """
    usages: list[str] = []

    if project_root is not None:
        project_manifest = project_manifest_path(project_root)
        if project_manifest.exists():
            try:
                packages = get_packages(project_manifest)
            except AiDotfilesError:
                packages = []
            if element_raw in packages:
                usages.append("ai-dotfiles.json")

    global_manifest = storage / "global.json"
    if global_manifest.exists():
        try:
            packages = get_packages(global_manifest)
        except AiDotfilesError:
            packages = []
        if element_raw in packages:
            usages.append("global.json")

    return usages


@click.command()
@click.argument("element_type", type=click.Choice(list(_VALID_TYPES)))
@click.argument("name")
def create(element_type: str, name: str) -> None:
    """Create a standalone ELEMENT_TYPE called NAME in catalog/."""
    try:
        # Validate NAME via the shared element parser (same rules as elsewhere).
        parse_element(f"{element_type}:{name}")

        catalog = catalog_dir()
        dest = _element_path(element_type, name, catalog)

        if dest.exists():
            raise ElementError(f"{element_type}:{name} already exists at {dest}")

        if element_type == "skill":
            dest.mkdir(parents=True, exist_ok=False)
            created = generate_element_from_template(element_type, name, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            created = generate_element_from_template(element_type, name, dest)

        try:
            rel = created.relative_to(storage_root())
            ui.success(f"Created {rel}")
        except ValueError:
            ui.success(f"Created {created}")

    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@click.command()
@click.argument("element_type", type=click.Choice(list(_VALID_TYPES)))
@click.argument("name", shell_complete=make_completer(complete_standalone_elements))
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt.")
def delete(element_type: str, name: str, force: bool) -> None:
    """Delete a standalone ELEMENT_TYPE called NAME from catalog/."""
    try:
        parse_element(f"{element_type}:{name}")

        catalog = catalog_dir()
        target = _element_path(element_type, name, catalog)

        if not target.exists():
            raise ElementError(f"{element_type}:{name} not found at {target}")

        element_raw = f"{element_type}:{name}"
        storage = storage_root()
        project_root = find_project_root()
        usages = find_usage(element_raw, storage, project_root)

        if usages:
            ui.warn(f"{element_raw} is used in: {', '.join(usages)}")

        if not force and not ui.confirm(f"Delete {element_raw}?", default=False):
            ui.info("Aborted.")
            return

        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

        try:
            rel = target.relative_to(storage_root())
            suffix = "/" if element_type == "skill" else ""
            ui.success(f"Deleted {rel}{suffix}")
        except ValueError:
            ui.success(f"Deleted {target}")

    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
