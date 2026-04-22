"""``ai-dotfiles stack`` — manage and apply stack preset files.

A stack is a newline-delimited ``.conf`` file under
``<storage_root>/stacks/<name>.conf`` listing element specifiers (one per
line). Lines starting with ``#`` and blank lines are ignored. Applying a
stack adds every listed element to the current project's manifest and sets
the ``stack`` metadata key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import manifest, symlinks
from ai_dotfiles.core.completions import (
    complete_available_specifiers,
    complete_stack_items,
    complete_stack_names,
    make_completer,
)
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_element,
    parse_elements,
    resolve_target_paths,
    validate_element_exists,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.paths import (
    backup_dir,
    catalog_dir,
    find_project_root,
    project_claude_dir,
    project_manifest_path,
    stacks_dir,
)
from ai_dotfiles.core.settings_merge import (
    assemble_settings,
    collect_domain_fragments,
    write_settings,
)

# ── Helpers ───────────────────────────────────────────────────────────────


def _stack_path(name: str) -> Path:
    """Return ``stacks/<name>.conf`` path."""
    return stacks_dir() / f"{name}.conf"


def _read_stack(path: Path) -> list[str]:
    """Parse a ``.conf`` file, returning element specifiers.

    Skips blank lines and ``#`` comments.
    """
    if not path.exists():
        raise ConfigError(f"Stack file {path} does not exist")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read stack {path}: {exc}") from exc
    items: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        items.append(stripped)
    return items


def _write_stack(path: Path, items: list[str], name: str) -> None:
    """Write a ``.conf`` file with a header followed by the items."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Stack: {name}\n"
            f"# Apply with: ai-dotfiles stack apply {name}\n"
            "# One element per line. Lines starting with # are comments.\n"
        )
        body = "".join(f"{item}\n" for item in items)
        path.write_text(header + body, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot write stack {path}: {exc}") from exc


def _resolve_project() -> tuple[Path, Path]:
    """Return ``(manifest_path, claude_dir)`` for the current project."""
    root = find_project_root()
    if root is None:
        raise ConfigError(
            "No project found. Run 'ai-dotfiles init' first before applying a stack."
        )
    return project_manifest_path(root), project_claude_dir(root)


def _link_element(element: Element, claude_dir: Path, catalog: Path) -> None:
    """Create symlinks for ``element`` into ``claude_dir``."""
    pairs = resolve_target_paths(element, claude_dir, catalog)
    for source, target in pairs:
        symlinks.safe_symlink(source, target, backup_dir())


def _rebuild_settings(manifest_path: Path, claude_dir: Path, catalog: Path) -> None:
    """Reassemble ``settings.json`` from all domain fragments in the manifest."""
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    write_settings(assemble_settings(fragments), claude_dir / "settings.json")


# ── Click group ───────────────────────────────────────────────────────────


@click.group()
def stack() -> None:
    """Manage ``.conf`` stack presets."""


@stack.command("create")
@click.argument("name")
def create_stack(name: str) -> None:
    """Create a new empty stack named NAME."""
    try:
        path = _stack_path(name)
        if path.exists():
            raise ConfigError(f"Stack {name!r} already exists at {path}")
        _write_stack(path, [], name)
        rel = path.relative_to(stacks_dir().parent)
        ui.success(f"Created stack {name} at {rel}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@stack.command("delete")
@click.argument("name", shell_complete=make_completer(complete_stack_names))
def delete_stack(name: str) -> None:
    """Delete the stack NAME."""
    try:
        path = _stack_path(name)
        if not path.exists():
            raise ConfigError(f"Stack {name!r} not found at {path}")
        try:
            path.unlink()
        except OSError as exc:
            raise ConfigError(f"Cannot delete stack {path}: {exc}") from exc
        ui.success(f"Deleted stack {name}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@stack.command("list")
@click.argument("name", shell_complete=make_completer(complete_stack_names))
def list_stack(name: str) -> None:
    """List the contents of stack NAME."""
    try:
        path = _stack_path(name)
        if not path.exists():
            raise ConfigError(f"Stack {name!r} not found at {path}")
        items = _read_stack(path)
        if not items:
            ui.info(f"Stack {name} is empty")
            return
        ui.info(f"Stack {name}:")
        for item in items:
            ui.info(f"  {item}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@stack.command("add")
@click.argument("name", shell_complete=make_completer(complete_stack_names))
@click.argument(
    "items",
    nargs=-1,
    required=True,
    shell_complete=make_completer(complete_available_specifiers),
)
def add_to_stack(name: str, items: tuple[str, ...]) -> None:
    """Append ITEMS to stack NAME (duplicates skipped)."""
    try:
        path = _stack_path(name)
        if not path.exists():
            raise ConfigError(f"Stack {name!r} not found at {path}")

        # Validate format by parsing (raises ElementError on bad input).
        parse_elements(list(items))

        existing = _read_stack(path)
        added: list[str] = []
        skipped: list[str] = []
        for item in items:
            if item in existing or item in added:
                skipped.append(item)
            else:
                added.append(item)

        if added:
            _write_stack(path, existing + added, name)
            ui.info(f"Added to stack {name}:")
            for item in added:
                ui.success(item)
        else:
            ui.info(f"Nothing added to stack {name}")

        for item in skipped:
            ui.info(f"  ~ {item} (already in stack)")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@stack.command("remove")
@click.argument("name", shell_complete=make_completer(complete_stack_names))
@click.argument(
    "items",
    nargs=-1,
    required=True,
    shell_complete=make_completer(complete_stack_items),
)
def remove_from_stack(name: str, items: tuple[str, ...]) -> None:
    """Remove ITEMS from stack NAME."""
    try:
        path = _stack_path(name)
        if not path.exists():
            raise ConfigError(f"Stack {name!r} not found at {path}")

        existing = _read_stack(path)
        remaining = list(existing)
        removed: list[str] = []
        for item in items:
            if item in remaining:
                remaining.remove(item)
                removed.append(item)
            else:
                ui.warn(f"{item} not in stack {name}")

        if removed:
            _write_stack(path, remaining, name)
            ui.info(f"Removed from stack {name}:")
            for item in removed:
                ui.info(f"  - {item}")
        else:
            ui.info(f"Nothing removed from stack {name}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@stack.command("apply")
@click.argument("name", shell_complete=make_completer(complete_stack_names))
def apply_stack(name: str) -> None:
    """Apply stack NAME to the current project's manifest."""
    try:
        path = _stack_path(name)
        if not path.exists():
            raise ConfigError(f"Stack {name!r} not found at {path}")

        items = _read_stack(path)
        if not items:
            ui.warn(f"Stack {name} is empty; nothing to apply")
            return

        # Validate specifiers before touching anything.
        elements = [parse_element(item) for item in items]

        catalog = catalog_dir()
        for element in elements:
            validate_element_exists(element, catalog)

        manifest_path, claude_dir = _resolve_project()
        claude_dir.mkdir(parents=True, exist_ok=True)

        raw_items = [element.raw for element in elements]
        added = manifest.add_packages(manifest_path, raw_items)
        added_set = set(added)

        ui.info(f"Applying stack {name}:")
        for element in elements:
            if element.raw in added_set:
                _link_element(element, claude_dir, catalog)
                ui.success(element.raw)
            else:
                ui.info(f"  ~ {element.raw} (already installed)")

        manifest.set_metadata(manifest_path, "stack", name)

        has_domain = any(el.type is ElementType.DOMAIN for el in elements)
        if has_domain:
            _rebuild_settings(manifest_path, claude_dir, catalog)
            ui.info(f"Settings: rebuilt {claude_dir.name}/settings.json")
        else:
            _rebuild_settings(manifest_path, claude_dir, catalog)

        ui.info(f"Applied stack {name}: {len(added)} packages added")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
