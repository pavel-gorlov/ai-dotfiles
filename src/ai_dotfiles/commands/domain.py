"""``ai-dotfiles domain`` — manage domains in the catalog.

Subcommands:

* ``create <name>``          — scaffold a new domain directory
* ``delete <name>``          — remove an existing domain
* ``list <name>``            — list the contents of a domain grouped by type
* ``add <name> <type> <el>`` — add a skill/agent/rule element inside a domain
* ``remove <name> <type> <el>`` — remove a skill/agent/rule element from a domain
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import manifest, symlinks
from ai_dotfiles.core.completions import (
    complete_domain_elements,
    complete_domain_names,
    make_completer,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, ElementError
from ai_dotfiles.core.paths import (
    backup_dir,
    catalog_dir,
    claude_global_dir,
    find_project_root,
    global_manifest_path,
    project_claude_dir,
    project_manifest_path,
    storage_root,
)
from ai_dotfiles.scaffold.generator import generate_element_from_template

_ELEMENT_TYPES = ("skill", "agent", "rule")
_DOMAIN_SUBDIRS = ("skills", "agents", "rules", "hooks")


def _domain_path(name: str) -> Path:
    return catalog_dir() / name


def _require_domain_exists(name: str) -> Path:
    path = _domain_path(name)
    if not path.is_dir():
        raise ElementError(f"Domain @{name} not found at {path}")
    return path


def _find_usage(name: str) -> list[Path]:
    """Return paths of manifests that reference ``@name``.

    Scans ``global.json`` only. We cannot reliably discover arbitrary
    project manifests from here, so this is a best-effort warning.
    """
    specifier = f"@{name}"
    hits: list[Path] = []

    global_manifest = storage_root() / "global.json"
    if global_manifest.is_file():
        try:
            pkgs = manifest.get_packages(global_manifest)
        except ConfigError:
            pkgs = []
        if specifier in pkgs:
            hits.append(global_manifest)

    return hits


def _element_dest(domain_root: Path, element_type: str, element_name: str) -> Path:
    if element_type == "skill":
        return domain_root / "skills" / element_name
    if element_type == "agent":
        return domain_root / "agents" / f"{element_name}.md"
    if element_type == "rule":
        return domain_root / "rules" / f"{element_name}.md"
    raise ElementError(f"Unknown element type: {element_type!r}")


def _element_subpath(element_type: str, element_name: str) -> Path:
    """Path of the element relative to a ``.claude/`` directory."""
    if element_type == "skill":
        return Path("skills") / element_name
    if element_type == "agent":
        return Path("agents") / f"{element_name}.md"
    if element_type == "rule":
        return Path("rules") / f"{element_name}.md"
    raise ElementError(f"Unknown element type: {element_type!r}")


def _element_exists(dest: Path, element_type: str) -> bool:
    if element_type == "skill":
        return dest.is_dir()
    return dest.is_file()


def _domain_install_targets(name: str) -> list[tuple[str, Path]]:
    """Return ``(label, claude_dir)`` for every manifest where ``@name`` lives.

    Best effort — only inspects the global manifest and the project at cwd.
    Other projects are out of reach from a single CLI invocation.
    """
    specifier = f"@{name}"
    targets: list[tuple[str, Path]] = []

    global_manifest = global_manifest_path()
    if global_manifest.is_file():
        try:
            pkgs = manifest.get_packages(global_manifest)
        except ConfigError:
            pkgs = []
        if specifier in pkgs:
            targets.append(("global", claude_global_dir()))

    project_root = find_project_root()
    if project_root is not None:
        proj_manifest = project_manifest_path(project_root)
        if proj_manifest.is_file():
            try:
                pkgs = manifest.get_packages(proj_manifest)
            except ConfigError:
                pkgs = []
            if specifier in pkgs:
                targets.append((project_root.name, project_claude_dir(project_root)))

    return targets


@click.group()
def domain() -> None:
    """Manage domains in catalog/."""


@domain.command("create")
@click.argument("name")
def create(name: str) -> None:
    """Create a new domain at catalog/<NAME>/."""
    try:
        if name.startswith("_") and name != "_example":
            raise ElementError(
                f"Domain name {name!r} is reserved "
                "(names starting with '_' are reserved)."
            )

        path = _domain_path(name)
        if path.exists():
            raise ConfigError(f"Domain @{name} already exists at {path}")

        for sub in _DOMAIN_SUBDIRS:
            (path / sub).mkdir(parents=True, exist_ok=True)

        meta = {
            "name": name,
            "description": f"{name} domain — edit or remove",
        }
        (path / "domain.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )

        ui.success(f"Created domain @{name} at catalog/{name}/")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@domain.command("delete")
@click.argument("name", shell_complete=make_completer(complete_domain_names))
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def delete(name: str, yes: bool) -> None:
    """Delete the domain at catalog/<NAME>/."""
    try:
        if name == "_example":
            raise ElementError(
                "Cannot delete domain @_example (reserved scaffolding stub)."
            )

        path = _require_domain_exists(name)

        usage = _find_usage(name)
        if usage:
            ui.warn(f"Domain @{name} is referenced in:")
            for hit in usage:
                ui.warn(f"  - {hit}")

        if not yes and not ui.confirm(f"Delete domain @{name}?", default=False):
            ui.info("Aborted.")
            return

        shutil.rmtree(path)
        ui.success(f"Deleted domain @{name}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@domain.command("list")
@click.argument("name", shell_complete=make_completer(complete_domain_names))
def list_domain(name: str) -> None:
    """List the contents of catalog/<NAME>/."""
    try:
        path = _require_domain_exists(name)

        ui.info(f"Domain @{name}:")
        for sub in ("skills", "agents", "rules", "hooks"):
            ui.info(f"  {sub}:")
            sub_dir = path / sub
            if not sub_dir.is_dir():
                ui.info("    (empty)")
                continue

            entries: list[str] = []
            for entry in sorted(sub_dir.iterdir()):
                if entry.name.startswith("."):
                    continue
                if sub == "skills":
                    if entry.is_dir():
                        entries.append(entry.name)
                elif sub in {"agents", "rules"}:
                    if entry.is_file() and entry.suffix == ".md":
                        entries.append(entry.stem)
                else:  # hooks
                    if entry.is_file():
                        entries.append(entry.name)

            if not entries:
                ui.info("    (empty)")
            else:
                for item in entries:
                    ui.info(f"    {item}")

        meta = path / "domain.json"
        ui.info(f"  domain.json: {'yes' if meta.is_file() else 'no'}")
        fragment = path / "settings.fragment.json"
        ui.info(f"  settings.fragment.json: {'yes' if fragment.is_file() else 'no'}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@domain.command("add")
@click.argument("name", shell_complete=make_completer(complete_domain_names))
@click.argument("element_type", type=click.Choice(list(_ELEMENT_TYPES)))
@click.argument("element_name")
def add_element(name: str, element_type: str, element_name: str) -> None:
    """Create an ELEMENT_TYPE element named ELEMENT_NAME inside domain NAME.

    If ``@<NAME>`` is already in the global or current-project manifest, the
    new element is symlinked into the corresponding ``.claude/`` directory
    so users do not have to chase a follow-up ``install`` invocation.
    """
    try:
        domain_root = _require_domain_exists(name)
        dest = _element_dest(domain_root, element_type, element_name)

        if _element_exists(dest, element_type):
            raise ConfigError(
                f"{element_type.capitalize()} {element_name!r} already exists "
                f"in domain @{name}"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        if element_type == "skill":
            dest.mkdir(parents=True, exist_ok=True)
        generate_element_from_template(element_type, element_name, dest)

        ui.success(f"Created {element_type} {element_name} in domain @{name}")

        targets = _domain_install_targets(name)
        if targets:
            sub = _element_subpath(element_type, element_name)
            backup = backup_dir()
            for label, claude_dir in targets:
                target = claude_dir / sub
                symlinks.safe_symlink(dest, target, backup)
                ui.success(f"Linked {sub} into {label}/.claude/")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@domain.command("remove")
@click.argument("name", shell_complete=make_completer(complete_domain_names))
@click.argument("element_type", type=click.Choice(list(_ELEMENT_TYPES)))
@click.argument(
    "element_name",
    shell_complete=make_completer(complete_domain_elements),
)
def remove_element(name: str, element_type: str, element_name: str) -> None:
    """Remove ELEMENT_NAME (of ELEMENT_TYPE) from domain NAME.

    Any matching symlinks under installed scopes (global / current project)
    are unlinked first so they don't dangle once the catalog entry is gone.
    """
    try:
        domain_root = _require_domain_exists(name)
        dest = _element_dest(domain_root, element_type, element_name)

        if not _element_exists(dest, element_type):
            raise ElementError(
                f"{element_type.capitalize()} {element_name!r} not found in "
                f"domain @{name}"
            )

        sub = _element_subpath(element_type, element_name)
        for label, claude_dir in _domain_install_targets(name):
            target = claude_dir / sub
            if symlinks.remove_symlink(target):
                ui.info(f"Unlinked {sub} from {label}/.claude/")

        if element_type == "skill":
            shutil.rmtree(dest)
        else:
            dest.unlink()

        ui.success(f"Removed {element_type} {element_name} from domain @{name}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
