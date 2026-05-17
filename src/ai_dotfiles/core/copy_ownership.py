"""Ownership state for copy-mode installs into ``.claude/``.

In ``link_mode: "copy"`` the Claude target writes *real* files into
``.claude/skills``, ``.claude/agents`` and ``.claude/rules`` instead of
symlinks (see :mod:`ai_dotfiles.core.fs_copy`). A symlink into the
catalog is self-identifying as ai-dotfiles-managed — its target resolves
into storage. A copied file is indistinguishable from one the user
authored by hand.

This sidecar closes that gap: after every copy-mode ``install`` / ``add``
it records the ``.claude``-relative path of each copied entry. ``remove``
and ``install --prune`` consult it so a stale copy is cleaned up and a
user-authored file under ``.claude/`` is never deleted; ``status`` uses
it to report copies as managed-and-OK rather than "unmanaged real file".

Location: ``<claude_dir>/.ai-dotfiles-copies.json`` — a sidecar next to
``settings.json``, mirroring :mod:`settings_ownership`.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-copies.json"


def ownership_path(claude_dir: Path) -> Path:
    """Return the copy-ownership file path for a ``.claude`` dir."""
    return claude_dir / OWNERSHIP_FILENAME


def load_copy_ownership(claude_dir: Path) -> set[str]:
    """Load the set of ``.claude``-relative paths of managed copies.

    Returns an empty set if the file is absent. Raises
    :class:`ConfigError` on invalid JSON or wrong shape.
    """
    path = ownership_path(claude_dir)
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object at top level")
    entries = data.get("entries", [])
    if not isinstance(entries, list) or not all(
        isinstance(item, str) for item in entries
    ):
        raise ConfigError(f"{path}: 'entries' must be a list of strings")
    return set(entries)


def save_copy_ownership(claude_dir: Path, entries: set[str]) -> None:
    """Atomically write the managed-copy set (deterministic ordering).

    Deletes the sidecar instead of writing an empty list, so a project
    that switches back to ``link_mode: "symlink"`` leaves no orphan file.
    """
    path = ownership_path(claude_dir)
    if not entries:
        delete_copy_ownership(claude_dir)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": sorted(entries)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def delete_copy_ownership(claude_dir: Path) -> None:
    """Remove the copy-ownership file if present; silent if already gone."""
    path = ownership_path(claude_dir)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def relative_label(target: Path, claude_dir: Path) -> str:
    """Return ``target`` as a forward-slash path relative to ``claude_dir``.

    The label is the stable key stored in the sidecar — e.g.
    ``skills/code-review``. Falls back to the absolute path string for a
    target outside ``claude_dir`` (should not happen for Claude targets).
    """
    try:
        rel = target.relative_to(claude_dir)
    except ValueError:
        return str(target)
    return rel.as_posix()
