"""Element specifier parsing and path resolution.

Elements are the installable units referenced in manifests and on the CLI:

* ``@domain``    — a bundle of skills/agents/rules/hooks grouped under a theme
* ``skill:name`` — a single skill (directory with ``SKILL.md`` + assets)
* ``agent:name`` — a single agent (``.md`` file)
* ``rule:name``  — a single rule (``.md`` file)

This module only deals with *parsing* specifiers and *resolving* them to paths
inside the catalog. It performs no I/O beyond ``Path.exists``/``Path.iterdir``
in the resolver helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from ai_dotfiles.core.errors import ElementError

if TYPE_CHECKING:
    from ai_dotfiles.core.targets import Target

__all__ = [
    "Element",
    "ElementType",
    "parse_element",
    "parse_elements",
    "resolve_source_path",
    "resolve_target_paths",
    "validate_element_exists",
]


# Alphanumeric, hyphen, underscore. No slashes, dots, or other punctuation.
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")

# Files to skip when expanding a domain's subdirectories.
_DOMAIN_SKIP_FILES: frozenset[str] = frozenset(
    {"README.md", "domain.json", "settings.fragment.json", "mcp.fragment.json"}
)

# Subdirectories of a domain that contain linkable elements, mapped to the
# corresponding sub-path under ``claude_dir``.
_DOMAIN_SUBDIRS: tuple[str, ...] = ("skills", "agents", "rules", "hooks")


class ElementType(Enum):
    """Kind of element referenced by a specifier."""

    DOMAIN = "domain"
    SKILL = "skill"
    AGENT = "agent"
    RULE = "rule"


@dataclass(frozen=True)
class Element:
    """A parsed element specifier.

    ``raw`` preserves the exact original string, useful for error messages and
    round-tripping into manifests.
    """

    type: ElementType
    name: str
    raw: str


def _validate_name(name: str, raw: str) -> None:
    if not name or not _NAME_RE.match(name):
        raise ElementError(
            f"Invalid element name {name!r} in specifier {raw!r}: "
            "names must be alphanumeric with optional hyphens/underscores."
        )


def _validate_domain_name(name: str, raw: str) -> None:
    _validate_name(name, raw)
    # Domain names starting with `_` are reserved, except the `_example` stub
    # shipped for scaffolding.
    if name.startswith("_") and name != "_example":
        raise ElementError(
            f"Domain name {name!r} in {raw!r} is reserved "
            "(names starting with '_' are reserved)."
        )


def parse_element(s: str) -> Element:
    """Parse a single element specifier string.

    Accepted formats::

        @domain       -> Element(DOMAIN, "domain",  "@domain")
        skill:name    -> Element(SKILL,  "name",    "skill:name")
        agent:name    -> Element(AGENT,  "name",    "agent:name")
        rule:name     -> Element(RULE,   "name",    "rule:name")

    Raises ``ElementError`` for any malformed or unknown specifier.
    """
    if not isinstance(s, str):  # pragma: no cover - defensive
        raise ElementError(
            f"Element specifier must be a string, got {type(s).__name__}"
        )

    raw = s
    stripped = s.strip()
    if not stripped:
        raise ElementError("Empty element specifier.")

    if stripped.startswith("@"):
        name = stripped[1:]
        _validate_domain_name(name, raw)
        return Element(ElementType.DOMAIN, name, raw)

    if ":" not in stripped:
        raise ElementError(
            f"Invalid element specifier {raw!r}: expected '@domain' or "
            "'<type>:<name>' where <type> is one of skill, agent, rule."
        )

    prefix, _, name = stripped.partition(":")
    prefix = prefix.strip()
    name = name.strip()

    mapping: dict[str, ElementType] = {
        "skill": ElementType.SKILL,
        "agent": ElementType.AGENT,
        "rule": ElementType.RULE,
    }
    if prefix not in mapping:
        raise ElementError(
            f"Unknown element type {prefix!r} in specifier {raw!r}: "
            "expected one of 'skill', 'agent', 'rule'."
        )

    _validate_name(name, raw)
    return Element(mapping[prefix], name, raw)


def parse_elements(items: list[str]) -> list[Element]:
    """Parse multiple specifiers. Short-circuits on the first invalid entry."""
    return [parse_element(item) for item in items]


def resolve_source_path(element: Element, catalog: Path) -> Path:
    """Return the canonical source path of ``element`` inside ``catalog``.

    The returned path is not guaranteed to exist — use
    :func:`validate_element_exists` for that.
    """
    if element.type is ElementType.DOMAIN:
        return catalog / element.name
    if element.type is ElementType.SKILL:
        return catalog / "skills" / element.name
    if element.type is ElementType.AGENT:
        return catalog / "agents" / f"{element.name}.md"
    if element.type is ElementType.RULE:
        return catalog / "rules" / f"{element.name}.md"
    raise ElementError(  # pragma: no cover - exhaustive
        f"Unsupported element type: {element.type!r}"
    )


def _domain_target_pairs(
    element: Element, config_dir: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    domain_root = catalog / element.name
    pairs: list[tuple[Path, Path]] = []
    for subdir in _DOMAIN_SUBDIRS:
        source_dir = domain_root / subdir
        if not source_dir.is_dir():
            continue
        target_dir = config_dir / subdir
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES:
                continue
            # Skip hidden files (e.g. .DS_Store) to keep output deterministic.
            if entry.name.startswith("."):
                continue
            pairs.append((entry, target_dir / entry.name))
    return pairs


def _claude_target_pairs(
    element: Element, claude_dir: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    if element.type is ElementType.DOMAIN:
        return _domain_target_pairs(element, claude_dir, catalog)

    source = resolve_source_path(element, catalog)
    if element.type is ElementType.SKILL:
        return [(source, claude_dir / "skills" / element.name)]
    if element.type is ElementType.AGENT:
        return [(source, claude_dir / "agents" / f"{element.name}.md")]
    if element.type is ElementType.RULE:
        return [(source, claude_dir / "rules" / f"{element.name}.md")]
    raise ElementError(  # pragma: no cover - exhaustive
        f"Unsupported element type: {element.type!r}"
    )


def _codex_pair_for(
    element_type: ElementType, name: str, source: Path, project_root: Path, raw: str
) -> tuple[Path, Path]:
    """Return the ``(source, target)`` pair for one Codex skill or agent.

    Codex skills land under ``.agents/skills/<name>/`` and Codex agents
    under ``.codex/agents/<name>.toml`` — two distinct roots, unlike the
    single ``.claude`` tree. Element types with no Phase-1 Codex surface
    (rules, hooks) raise :class:`ElementError`.
    """
    # Imported lazily: ``core.paths`` depends on this module's ``ElementType``,
    # so a top-level import would cycle.
    from ai_dotfiles.core import paths

    if element_type is ElementType.SKILL:
        return (source, paths.project_codex_skills_dir(project_root) / name)
    if element_type is ElementType.AGENT:
        return (source, paths.project_codex_agents_dir(project_root) / f"{name}.toml")
    raise ElementError(
        f"Element type {element_type.value!r} has no Codex target surface "
        f"(specifier {raw!r})."
    )


def _codex_target_pairs(
    element: Element, project_root: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    if element.type is ElementType.DOMAIN:
        # Expand the domain into its member skills/agents and resolve each
        # for the Codex target. Rules and hooks have no Phase-1 surface.
        domain_root = catalog / element.name
        pairs: list[tuple[Path, Path]] = []
        for subdir, member_type in (
            ("skills", ElementType.SKILL),
            ("agents", ElementType.AGENT),
        ):
            source_dir = domain_root / subdir
            if not source_dir.is_dir():
                continue
            for entry in sorted(source_dir.iterdir()):
                if entry.name in _DOMAIN_SKIP_FILES or entry.name.startswith("."):
                    continue
                name = entry.stem if member_type is ElementType.AGENT else entry.name
                pairs.append(
                    _codex_pair_for(member_type, name, entry, project_root, element.raw)
                )
        return pairs

    source = resolve_source_path(element, catalog)
    return [
        _codex_pair_for(element.type, element.name, source, project_root, element.raw)
    ]


def resolve_target_paths(
    element: Element,
    config_root: Path,
    catalog: Path,
    target: Target | None = None,
) -> list[tuple[Path, Path]]:
    """Return ``(source, target)`` pairs to materialise ``element`` for ``target``.

    ``target`` defaults to :data:`Target.CLAUDE`; the Claude resolution is
    byte-identical to the pre-multi-target behaviour. For Claude,
    ``config_root`` is the ``.claude`` directory; for Codex it is the
    project root (Codex spreads skills and agents across two distinct
    sub-trees).

    For :data:`ElementType.DOMAIN`, the domain is expanded into its member
    elements. For standalone types, a single pair is returned. The Codex
    target raises :class:`ElementError` for element types with no Phase-1
    Codex surface (e.g. rules).
    """
    # Imported lazily to avoid a module-level import cycle (``targets``
    # imports ``ElementType`` from this module).
    from ai_dotfiles.core.targets import Target as _Target

    effective = _Target.CLAUDE if target is None else target
    if effective is _Target.CLAUDE:
        return _claude_target_pairs(element, config_root, catalog)
    return _codex_target_pairs(element, config_root, catalog)


def validate_element_exists(element: Element, catalog: Path) -> None:
    """Raise :class:`ElementError` if ``element`` is not present in ``catalog``."""
    source = resolve_source_path(element, catalog)
    if not source.exists():
        raise ElementError(
            f"Element {element.raw!r} not found in catalog: {source} does not exist."
        )
