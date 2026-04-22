"""Safe symlink management with backup, idempotency, and chmod support.

Core primitives used by install / add / remove operations. Every public
function raises :class:`LinkError` on failure.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from ai_dotfiles.core.errors import LinkError

# Names that must never be linked from a catalog into ~/.claude/.
_SKIP_NAMES: frozenset[str] = frozenset({"README.md", "settings.fragment.json"})

# Domain subdirectories that are candidates for linking.
_DOMAIN_SUBDIRS: tuple[str, ...] = ("skills", "agents", "rules", "hooks")


def _chmod_plus_x(path: Path) -> None:
    """Set executable bits on ``path`` if it is a regular file."""
    try:
        current = path.stat().st_mode
        path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:  # pragma: no cover - defensive
        raise LinkError(f"Failed to chmod +x {path}: {exc}") from exc


def _maybe_chmod_sh(source: Path) -> None:
    """chmod +x on ``source`` if it is a .sh file."""
    if source.is_file() and source.suffix == ".sh":
        _chmod_plus_x(source)


def _backup_target_for(target: Path, backup_root: Path) -> Path:
    """Compute the backup location for ``target`` under ``backup_root``.

    The backup preserves the path of ``target`` relative to the user's home
    directory so ``~/.claude/hooks/lint.sh`` is backed up to
    ``<backup_root>/.claude/hooks/lint.sh``. For targets outside home the full
    absolute path (without anchor) is used.
    """
    target_abs = target.resolve() if target.exists() else target.absolute()
    home = Path.home()
    try:
        rel = target_abs.relative_to(home)
    except ValueError:
        # Strip anchor (drive/root) and use the remaining path.
        rel = Path(*target_abs.parts[1:]) if target_abs.is_absolute() else target_abs
    return backup_root / rel


def safe_symlink(
    source: Path, target: Path, backup: Path, *, adopt: bool = False
) -> str:
    """Create symlink ``target`` -> ``source`` idempotently.

    Returns one of: ``"linked"``, ``"already-linked"``, ``"relinked"``,
    ``"backed-up"``, ``"adopted"``.

    When ``adopt`` is True and ``target`` exists as a real file or directory,
    the target's content replaces ``source`` (so the user's pre-existing
    content becomes the source of truth) instead of being moved to ``backup``.
    """
    source_abs = source.resolve() if source.exists() else source.absolute()
    if not source_abs.exists():
        raise LinkError(f"Source does not exist: {source}")

    # chmod +x applies before linking so the symlink inherits exec perms.
    _maybe_chmod_sh(source_abs)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LinkError(f"Failed to create parent dirs for {target}: {exc}") from exc

    status: str

    if target.is_symlink():
        try:
            current = Path(os.readlink(target))
        except OSError as exc:
            raise LinkError(f"Failed to read symlink {target}: {exc}") from exc
        current_abs = (
            current if current.is_absolute() else (target.parent / current)
        ).resolve()
        if current_abs == source_abs:
            return "already-linked"
        try:
            target.unlink()
        except OSError as exc:
            raise LinkError(
                f"Failed to remove existing symlink {target}: {exc}"
            ) from exc
        status = "relinked"
    elif target.exists():
        if adopt:
            try:
                if source_abs.is_dir() and not source_abs.is_symlink():
                    shutil.rmtree(source_abs)
                elif source_abs.exists() or source_abs.is_symlink():
                    source_abs.unlink()
                source_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(source_abs))
            except OSError as exc:
                raise LinkError(
                    f"Failed to adopt {target} -> {source_abs}: {exc}"
                ) from exc
            status = "adopted"
        else:
            dest = _backup_target_for(target, backup)
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or dest.is_symlink():
                    # Avoid shutil.move merging into an existing backup dir.
                    if dest.is_dir() and not dest.is_symlink():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(target), str(dest))
            except OSError as exc:
                raise LinkError(f"Failed to back up {target} -> {dest}: {exc}") from exc
            status = "backed-up"
    else:
        status = "linked"

    try:
        target.symlink_to(source_abs)
    except OSError as exc:
        raise LinkError(
            f"Failed to create symlink {target} -> {source_abs}: {exc}"
        ) from exc

    return status


def remove_symlink(target: Path) -> bool:
    """Remove ``target`` if it is a symlink. Return True if it was removed."""
    if not target.is_symlink():
        return False
    try:
        target.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to remove symlink {target}: {exc}") from exc
    return True


def is_managed_symlink(target: Path, storage: Path) -> bool:
    """Return True if ``target`` is a symlink pointing into ``storage``."""
    if not target.is_symlink():
        return False
    try:
        resolved = target.resolve()
        storage_abs = storage.resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(storage_abs)
    except ValueError:
        return False
    return True


def _iter_domain_items(domain_path: Path) -> list[tuple[str, Path]]:
    """Yield (subdir_name, item_path) pairs for linkable items in a domain."""
    items: list[tuple[str, Path]] = []
    for sub in _DOMAIN_SUBDIRS:
        sub_dir = domain_path / sub
        if not sub_dir.is_dir():
            continue
        for child in sorted(sub_dir.iterdir()):
            if child.name in _SKIP_NAMES:
                continue
            items.append((sub, child))
    return items


def link_domain(domain_path: Path, claude_dir: Path, backup: Path) -> list[str]:
    """Link every element inside ``domain_path`` into ``claude_dir``.

    Walks ``skills/``, ``agents/``, ``rules/``, ``hooks/``, skipping
    ``README.md`` and ``settings.fragment.json``. Each item (file or dir) is
    symlinked at ``claude_dir/<subdir>/<name>``.
    """
    if not domain_path.is_dir():
        raise LinkError(f"Domain path is not a directory: {domain_path}")

    messages: list[str] = []
    for sub, item in _iter_domain_items(domain_path):
        target = claude_dir / sub / item.name
        status = safe_symlink(item, target, backup)
        messages.append(f"{status} {sub}/{item.name}")
    return messages


def link_standalone(source: Path, target: Path, backup: Path) -> str:
    """Link a single standalone element, creating parent dirs as needed."""
    return safe_symlink(source, target, backup)


def unlink_domain(domain_path: Path, claude_dir: Path) -> list[str]:
    """Remove every symlink in ``claude_dir`` pointing into ``domain_path``."""
    if not claude_dir.is_dir():
        return []
    try:
        domain_abs = domain_path.resolve()
    except OSError as exc:
        raise LinkError(f"Failed to resolve domain {domain_path}: {exc}") from exc

    removed: list[str] = []
    for sub in _DOMAIN_SUBDIRS:
        sub_dir = claude_dir / sub
        if not sub_dir.is_dir():
            continue
        for child in sorted(sub_dir.iterdir()):
            if not child.is_symlink():
                continue
            try:
                resolved = child.resolve()
            except OSError:
                continue
            try:
                resolved.relative_to(domain_abs)
            except ValueError:
                continue
            if remove_symlink(child):
                removed.append(f"{sub}/{child.name}")
    return removed


def unlink_standalone(target: Path) -> bool:
    """Remove a standalone symlink at ``target``."""
    return remove_symlink(target)


def prune_dangling(claude_dir: Path, storage: Path) -> list[str]:
    """Remove dangling symlinks in ``claude_dir`` that point into ``storage``.

    Walks ``claude_dir/{skills,agents,rules,hooks}`` plus the top-level
    ``claude_dir`` for ``CLAUDE.md`` / ``settings.json`` style files. A symlink
    is pruned only when:

    1. it is a symlink (real files are never touched),
    2. its target resolves into ``storage`` (user's own symlinks pointing
       elsewhere stay put), and
    3. the resolved target no longer exists.

    Returns a list of removed labels like ``skills/foo``.
    """
    if not claude_dir.is_dir():
        return []
    try:
        storage_abs = storage.resolve()
    except OSError:
        return []

    removed: list[str] = []

    def _maybe_prune(entry: Path, label: str) -> None:
        if not entry.is_symlink():
            return
        try:
            raw = Path(os.readlink(entry))
        except OSError:
            return
        raw_abs = raw if raw.is_absolute() else (entry.parent / raw)
        try:
            resolved = raw_abs.resolve(strict=False)
        except OSError:
            return
        # Only touch symlinks into our own storage tree.
        try:
            resolved.relative_to(storage_abs)
        except ValueError:
            return
        # Not dangling — target still exists.
        if resolved.exists():
            return
        try:
            entry.unlink()
        except OSError:
            return
        removed.append(label)

    # Top-level managed files
    for top_name in ("CLAUDE.md", "settings.json"):
        _maybe_prune(claude_dir / top_name, top_name)

    # Managed subdirectories
    for sub in _DOMAIN_SUBDIRS + ("output-styles",):
        sub_dir = claude_dir / sub
        if not sub_dir.is_dir():
            continue
        for child in sorted(sub_dir.iterdir()):
            _maybe_prune(child, f"{sub}/{child.name}")

    return removed


def link_global_files(
    global_dir: Path, claude_dir: Path, backup: Path, *, adopt: bool = False
) -> list[str]:
    """Link ``global/`` contents into ``claude_dir`` file-by-file.

    Handles ``CLAUDE.md``, ``settings.json``, and every file inside
    ``hooks/`` and ``output-styles/`` individually (never a directory
    symlink). Skips ``README.md`` everywhere.

    When ``adopt`` is True, pre-existing target files are promoted into
    ``global_dir`` (replacing the scaffold templates) instead of being backed
    up. Use this on ``init -g`` so the user's existing ``~/.claude/`` config
    becomes the storage source of truth.
    """
    if not global_dir.is_dir():
        raise LinkError(f"Global dir does not exist: {global_dir}")

    messages: list[str] = []

    for top_name in ("CLAUDE.md", "settings.json"):
        src = global_dir / top_name
        if src.exists():
            status = safe_symlink(src, claude_dir / top_name, backup, adopt=adopt)
            messages.append(f"{status} {top_name}")

    for sub in ("hooks", "output-styles"):
        sub_dir = global_dir / sub
        if not sub_dir.is_dir():
            continue
        for child in sorted(sub_dir.iterdir()):
            if child.name == "README.md":
                continue
            target = claude_dir / sub / child.name
            status = safe_symlink(child, target, backup, adopt=adopt)
            messages.append(f"{status} {sub}/{child.name}")

    return messages
