"""Discover LOCAL (non-catalog) elements in a project's ``.claude/`` tree.

A *local* element is a hand-authored skill/agent/rule that lives as a real
file or directory under ``<project>/.claude/`` — it is **not** a symlink into
the ai-dotfiles storage (those are catalog-managed) and **not** declared in
the project manifest. Such elements are invisible to the manifest-driven
``install``/``status`` pipeline, which resolves every source from the catalog
(:func:`ai_dotfiles.core.elements.resolve_source_path`). This module walks the
project's own ``.claude/{skills,agents,rules}`` and yields the local ones so a
``migrate``/``status`` feature can carry them to the Codex target (or report
them as unmanaged) — see the Codex local-migration plan.

Discovery is provenance-based, not name-based:

* a catalog element materialises as a **symlink** whose target lives under
  :func:`ai_dotfiles.core.paths.storage_root` — those are skipped;
* an element named in the manifest is skipped even if the on-disk entry is a
  real file (a name collision the ``status`` command already flags as BROKEN);
* everything else that looks like a valid element is *local*.

The returned :class:`LocalElement` carries the real source path, so the same
``(source, target)`` machinery the catalog uses
(:func:`ai_dotfiles.core.elements._codex_pair_for`) can render it by treating
``project_claude_dir(root)`` as the "catalog" root — no change to those
signatures is required, because ``.claude/`` mirrors the catalog layout
(``skills/`` dirs, ``agents/*.md``, ``rules/*.md``).

This module performs read-only filesystem I/O (``iterdir``/``is_symlink``/
``resolve``); it never writes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core import paths
from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import AiDotfilesError

__all__ = ["LocalElement", "iter_local_elements"]


@dataclass(frozen=True)
class LocalElement:
    """A hand-authored element found in a project's ``.claude/`` tree.

    ``source_path`` is the real on-disk path (a skill *directory*, or an
    agent/rule ``.md`` file). ``raw`` is the canonical specifier form
    (``skill:foo`` / ``agent:foo`` / ``rule:foo``) so the value round-trips
    through :func:`ai_dotfiles.core.elements.parse_element` unchanged.
    """

    type: ElementType
    name: str
    source_path: Path
    raw: str


def iter_local_elements(
    project_root: Path,
    *,
    manifest_packages: Iterable[str] | None = None,
) -> Iterator[LocalElement]:
    """Yield the LOCAL (non-catalog, non-manifest) elements under ``.claude/``.

    Walks ``<project_root>/.claude/{skills,agents,rules}``. An entry is
    yielded only when it is a real file/dir (or a symlink that does **not**
    point into :func:`ai_dotfiles.core.paths.storage_root`) and its name is
    not present in ``manifest_packages``. Skills are directories containing a
    ``SKILL.md``; agents and rules are ``.md`` files. Hidden entries and
    names that fail :func:`ai_dotfiles.core.elements.parse_element` validation
    are ignored. Results are ordered ``skills`` → ``agents`` → ``rules``, each
    alphabetically. Nothing is yielded if ``.claude/`` is absent.
    """
    claude_dir = paths.project_claude_dir(project_root)
    if not claude_dir.is_dir():
        return

    storage = _resolved_storage()
    managed = _manifest_element_keys(manifest_packages)

    yield from _iter_skills(claude_dir / "skills", storage, managed)
    yield from _iter_markdown(
        claude_dir / "agents", ElementType.AGENT, "agent", storage, managed
    )
    yield from _iter_markdown(
        claude_dir / "rules", ElementType.RULE, "rule", storage, managed
    )


def _iter_skills(
    skills_dir: Path,
    storage: Path | None,
    managed: frozenset[tuple[str, str]],
) -> Iterator[LocalElement]:
    if not skills_dir.is_dir():
        return
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if _points_into_storage(entry, storage):
            continue
        if not entry.is_dir():
            continue
        if not (entry / "SKILL.md").is_file():
            continue
        name = entry.name
        if ("skill", name) in managed or not _valid_specifier("skill", name):
            continue
        yield LocalElement(ElementType.SKILL, name, entry, f"skill:{name}")


def _iter_markdown(
    dir_path: Path,
    element_type: ElementType,
    prefix: str,
    storage: Path | None,
    managed: frozenset[tuple[str, str]],
) -> Iterator[LocalElement]:
    if not dir_path.is_dir():
        return
    for entry in sorted(dir_path.iterdir()):
        if entry.name.startswith(".") or entry.suffix != ".md":
            continue
        if _points_into_storage(entry, storage):
            continue
        if not entry.is_file():
            continue
        name = entry.stem
        if (prefix, name) in managed or not _valid_specifier(prefix, name):
            continue
        yield LocalElement(element_type, name, entry, f"{prefix}:{name}")


def _resolved_storage() -> Path | None:
    try:
        return paths.storage_root().resolve()
    except OSError:  # pragma: no cover - unreadable storage path
        return None


def _points_into_storage(entry: Path, storage: Path | None) -> bool:
    """True when ``entry`` is a symlink resolving under the ai-dotfiles storage.

    Such an entry is a catalog-managed link, not a local element. A dangling
    symlink (target missing) is treated as *not* into storage so it is not
    silently swallowed here — it surfaces elsewhere as a broken link.
    """
    if storage is None or not entry.is_symlink():
        return False
    try:
        target = entry.resolve()
    except OSError:
        return False
    return target == storage or target.is_relative_to(storage)


def _valid_specifier(prefix: str, name: str) -> bool:
    try:
        parse_element(f"{prefix}:{name}")
    except AiDotfilesError:
        return False
    return True


def _manifest_element_keys(
    packages: Iterable[str] | None,
) -> frozenset[tuple[str, str]]:
    """Return ``(type_value, name)`` keys for the manifest's standalone elements.

    Domains are skipped: a domain's members materialise as catalog symlinks,
    which :func:`_points_into_storage` already excludes.
    """
    if not packages:
        return frozenset()
    keys: set[tuple[str, str]] = set()
    for spec in packages:
        try:
            element = parse_element(spec)
        except AiDotfilesError:
            continue
        if element.type is ElementType.DOMAIN:
            continue
        keys.add((element.type.value, element.name))
    return frozenset(keys)
