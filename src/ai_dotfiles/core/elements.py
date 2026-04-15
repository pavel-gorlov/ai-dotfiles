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

from ai_dotfiles.core.errors import ElementError

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
_DOMAIN_SKIP_FILES: frozenset[str] = frozenset({"README.md", "settings.fragment.json"})

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
    element: Element, claude_dir: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    domain_root = catalog / element.name
    pairs: list[tuple[Path, Path]] = []
    for subdir in _DOMAIN_SUBDIRS:
        source_dir = domain_root / subdir
        if not source_dir.is_dir():
            continue
        target_dir = claude_dir / subdir
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES:
                continue
            # Skip hidden files (e.g. .DS_Store) to keep output deterministic.
            if entry.name.startswith("."):
                continue
            pairs.append((entry, target_dir / entry.name))
    return pairs


def resolve_target_paths(
    element: Element, claude_dir: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    """Return ``(source, target)`` pairs to create symlinks for.

    For :data:`ElementType.DOMAIN`, this walks the domain's ``skills/``,
    ``agents/``, ``rules/`` and ``hooks/`` subdirectories and emits one pair
    per entry (skipping ``README.md`` and ``settings.fragment.json``, which
    are handled elsewhere).

    For standalone element types, a single pair is returned mirroring the
    source path under ``claude_dir``.
    """
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


def validate_element_exists(element: Element, catalog: Path) -> None:
    """Raise :class:`ElementError` if ``element`` is not present in ``catalog``."""
    source = resolve_source_path(element, catalog)
    if not source.exists():
        raise ElementError(
            f"Element {element.raw!r} not found in catalog: {source} does not exist."
        )
