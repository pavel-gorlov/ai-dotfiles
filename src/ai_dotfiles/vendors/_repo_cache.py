"""Shared git-backed cache for marketplace vendors.

Vendors that back onto a public git repository (e.g. ``buildwithclaude``,
``tonsofskills``) keep a local clone under
``$AI_DOTFILES_HOME/.vendor-cache/<vendor>/``. Callers ask
:func:`refresh` for a guaranteed-fresh path: the function clones on
first call, fetches+resets when the TTL expires, and is a no-op when
the cache is still fresh. :func:`find_skill_dirs` + :func:`read_frontmatter`
are walk helpers on top of the cached tree.

All git invocations go through an internal ``_run`` wrapper that maps
:class:`FileNotFoundError` (missing git binary) and non-zero exits
alike to :class:`~ai_dotfiles.core.errors.ExternalError`, so callers
only have to catch one exception type.
"""

from __future__ import annotations

import subprocess  # noqa: S404 — vendor cache intentionally shells out to git
import time
from collections.abc import Iterator
from pathlib import Path

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.core.paths import storage_root

CACHE_SUBDIR = ".vendor-cache"
_SENTINEL = ".fetched-at"
DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def cache_dir(vendor_name: str) -> Path:
    """Return ``$AI_DOTFILES_HOME/.vendor-cache/<vendor>/``.

    Does not create the directory. Callers (typically :func:`refresh`)
    are responsible for creating it when they actually need it.
    """
    return storage_root() / CACHE_SUBDIR / vendor_name


def is_fresh(cache_root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    """Return ``True`` when the sentinel exists and was touched within TTL."""
    sentinel = cache_root / _SENTINEL
    if not sentinel.is_file():
        return False
    age = time.time() - sentinel.stat().st_mtime
    return age < ttl_seconds


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke ``argv`` with ``check=False``; map failures to ExternalError.

    Both missing-binary (``FileNotFoundError``) and non-zero exit are
    surfaced as :class:`ExternalError`. Stdout/stderr are captured for
    error messages.
    """
    try:
        result = subprocess.run(  # noqa: S603 — argv built from trusted inputs
            argv,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ExternalError(
            "git executable not found on PATH; install from https://git-scm.com/."
        ) from exc
    if result.returncode != 0:
        raise ExternalError(
            f"git {argv[1] if len(argv) > 1 else ''} failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def _write_sentinel(cache_root: Path) -> None:
    sentinel = cache_root / _SENTINEL
    sentinel.touch()
    # Force mtime to current time (touch() does this on most platforms, but
    # be explicit so TTL checks are deterministic).
    now = time.time()
    import os

    os.utime(sentinel, (now, now))


def refresh(
    *,
    vendor_name: str,
    repo_url: str,
    branch: str = "main",
    force: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Path:
    """Guarantee an up-to-date local clone of ``repo_url`` for ``vendor_name``.

    Behaviour:

    * If the cache directory doesn't exist yet: ``git clone --depth=1``.
    * If the cache exists and is fresh (sentinel younger than TTL)
      and ``force=False``: no-op, return the cache path.
    * Otherwise: ``git fetch --depth=1`` then ``reset --hard origin/<branch>``.

    Writes ``<cache>/.fetched-at`` on every successful
    clone/fetch. Raises :class:`ExternalError` on any git failure.

    Note: no sparse-checkout — the target repos are small enough to
    full-clone at ``--depth=1``. Upgrade to sparse-checkout once repo
    size becomes a concern.
    """
    root = cache_dir(vendor_name)

    # Fresh-enough cache + no force = no work.
    if not force and root.is_dir() and is_fresh(root, ttl_seconds=ttl_seconds):
        return root

    root.parent.mkdir(parents=True, exist_ok=True)

    if not (root / ".git").is_dir():
        # First-time clone.
        if root.is_dir():
            # Cache dir exists but isn't a git repo (partial / corrupted).
            # Wipe it so the clone can proceed cleanly.
            import shutil

            shutil.rmtree(root)
        _run(["git", "clone", "--depth=1", "--branch", branch, repo_url, str(root)])
    else:
        _run(["git", "-C", str(root), "fetch", "--depth=1", "origin", branch])
        _run(["git", "-C", str(root), "reset", "--hard", f"origin/{branch}"])

    _write_sentinel(root)
    return root


def find_skill_dirs(cache_root: Path) -> Iterator[Path]:
    """Yield every directory inside ``cache_root`` containing a ``SKILL.md``.

    Recursively walks the tree, sorted for deterministic output, and
    skips hidden directories (``.git``, ``.cache``, etc.). A directory
    that contains ``SKILL.md`` is yielded; its children are *not*
    further descended into (one skill per directory).
    """

    def _walk(current: Path) -> Iterator[Path]:
        if not current.is_dir():
            return
        if (current / "SKILL.md").is_file():
            yield current
            return
        for entry in sorted(current.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            yield from _walk(entry)

    yield from _walk(cache_root)


def read_frontmatter(skill_md: Path) -> dict[str, str]:
    """Parse a minimal YAML-style frontmatter block from ``SKILL.md``.

    Expected shape::

        ---
        name: my-skill
        description: Does things.
        tags: [backend, api]
        ---

        (markdown body follows)

    * ``key: value`` lines become ``{key: value}`` with surrounding
      quotes stripped.
    * ``key: [a, b, c]`` becomes ``{key: "a, b, c"}`` — the list is
      serialised as a comma-space string so the rest of the system can
      keep treating everything as strings.
    * Missing or malformed frontmatter returns ``{}``.
    * Scanning stops at the second ``---``.
    """
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    result: dict[str, str] = {}
    i = 1
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped == "---":
            break
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        value = rest.strip()
        i += 1
        if not key:
            continue
        # YAML block scalars: `key: |` / `key: >` — collect following
        # indented lines until dedent or the closing `---`.
        if value in ("|", ">"):
            collected: list[str] = []
            while i < len(lines):
                line = lines[i]
                if line.strip() == "---":
                    break
                if not line.strip():
                    collected.append("")
                    i += 1
                    continue
                # Indented continuation.
                if line.startswith((" ", "\t")):
                    collected.append(line.strip())
                    i += 1
                    continue
                # Dedent — end of this key.
                break
            joiner = "\n" if value == "|" else " "
            value = joiner.join(collected).strip()
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            parts = [p.strip().strip("\"'") for p in inner.split(",")]
            value = ", ".join(p for p in parts if p)
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result
