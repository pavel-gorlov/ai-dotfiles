"""Copy-mode materialisation for the Claude target.

When a project manifest sets ``link_mode: "copy"`` the Claude target
writes *real* copied files into ``.claude/`` instead of symlinks into the
catalog (see :func:`ai_dotfiles.core.manifest.get_link_mode`). This is
the mode for a native-Windows host whose catalog lives in WSL — a
symlink into the catalog points at a path Windows tooling cannot
resolve.

This module is the copy-mode analogue of the symlink primitives in
:mod:`ai_dotfiles.core.symlinks`. It builds on:

* :func:`ai_dotfiles.core.fs_copy.copy_tree_into` — the actual copy;
* :mod:`ai_dotfiles.core.copy_ownership` — the sidecar recording which
  ``.claude/`` entries are managed copies (a copy, unlike a symlink, is
  not self-identifying).

Every public function raises :class:`LinkError` on a filesystem failure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ai_dotfiles.core.copy_ownership import (
    load_copy_ownership,
    relative_label,
    save_copy_ownership,
)
from ai_dotfiles.core.elements import Element, resolve_target_paths
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.fs_copy import copy_tree_into

__all__ = [
    "copy_element",
    "prune_copies",
    "remove_copied_element",
]


def copy_element(element: Element, claude_dir: Path, catalog: Path) -> list[str]:
    """Copy ``element``'s Claude-target content into ``claude_dir``.

    Each ``(source, target)`` pair the element resolves to is copied with
    :func:`copy_tree_into` (a directory recursively, a file directly,
    mode bits preserved). A pre-existing copy at ``target`` is replaced,
    so re-installing refreshes the snapshot.

    The ``.claude``-relative label of every copied target is recorded in
    the copy-ownership sidecar so :func:`remove_copied_element` and
    :func:`prune_copies` can act on it without deleting user files.

    Returns the list of recorded labels (e.g. ``["skills/code-review"]``).
    """
    pairs = resolve_target_paths(element, claude_dir, catalog)
    owned = load_copy_ownership(claude_dir)
    labels: list[str] = []
    for source, target in pairs:
        copy_tree_into(source, target)
        label = relative_label(target, claude_dir)
        owned.add(label)
        labels.append(label)
    save_copy_ownership(claude_dir, owned)
    return labels


def remove_copied_element(
    element: Element, claude_dir: Path, catalog: Path
) -> list[str]:
    """Delete the copied files ``element`` produced under ``claude_dir``.

    Only entries recorded in the copy-ownership sidecar are deleted, so a
    user-authored file of the same name under ``.claude/`` is never
    touched. The sidecar is updated to drop the removed labels.

    Returns the list of labels actually removed.
    """
    pairs = resolve_target_paths(element, claude_dir, catalog)
    owned = load_copy_ownership(claude_dir)
    removed: list[str] = []
    for _source, target in pairs:
        label = relative_label(target, claude_dir)
        if label not in owned:
            # Not an ai-dotfiles-managed copy — leave it alone.
            continue
        _delete_path(target)
        owned.discard(label)
        removed.append(label)
    save_copy_ownership(claude_dir, owned)
    return removed


def prune_copies(elements: list[Element], claude_dir: Path, catalog: Path) -> list[str]:
    """Delete managed copies no longer backed by the manifest.

    ``elements`` is the parsed manifest. The set of labels the manifest
    *wants* is derived from :func:`resolve_target_paths`; any label in the
    copy-ownership sidecar that is not wanted is a stale copy (e.g. after
    a manifest ``remove`` that crashed, or a catalog rename) and is
    deleted. User-authored files are never in the sidecar, so they are
    never pruned.

    Returns the list of pruned labels.
    """
    owned = load_copy_ownership(claude_dir)
    if not owned:
        return []
    wanted: set[str] = set()
    for element in elements:
        for _source, target in resolve_target_paths(element, claude_dir, catalog):
            wanted.add(relative_label(target, claude_dir))
    stale = sorted(owned - wanted)
    for label in stale:
        _delete_path(claude_dir / label)
        owned.discard(label)
    save_copy_ownership(claude_dir, owned)
    return stale


def _delete_path(path: Path) -> None:
    """Delete ``path`` whether it is a file, symlink or directory."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except OSError as exc:
        raise LinkError(f"Failed to remove copied entry {path}: {exc}") from exc
