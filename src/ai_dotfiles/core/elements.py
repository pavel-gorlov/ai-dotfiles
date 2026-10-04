"""Element specifier parsing and path resolution.

Elements are the installable units referenced in manifests and on the CLI:

* ``@domain``    — a bundle of skills/agents/rules/hooks grouped under a theme
* ``skill:name`` — a single skill (directory with ``SKILL.md`` + assets)
* ``agent:name`` — a single agent (``.md`` file)
* ``rule:name``  — a single rule (``.md`` file)

This module only deals with *parsing* specifiers and *resolving* them to paths
inside the catalog and target trees. Resolver helpers inspect domain directories
and read rule frontmatter to select the target's activation surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from ai_dotfiles.core.errors import ElementError

if TYPE_CHECKING:
    from ai_dotfiles.core.dsh_layout import DshLayout
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


def _codex_target_pairs(
    element: Element, project_root: Path, catalog: Path
) -> list[tuple[Path, Path]]:
    """Return the ``(source, target)`` pairs for the Codex target.

    Delegates to :mod:`ai_dotfiles.core.codex_targets` — the single home
    of the Codex path layout — flattening its typed
    ``CodexPair`` / ``CodexRulePlan`` results into plain tuples: a
    skill/agent/rule-skill pair contributes its rendered target, an
    always-on / path-scoped rule contributes one pair per ``AGENTS.md``
    its managed block lands in.

    A standalone rule whose file is absent (e.g. resolving a
    not-yet-installed element) yields no pairs rather than raising — the
    classifier needs a readable file.
    """
    # Imported lazily: ``codex_targets`` imports Element/ElementType from
    # this module, so a top-level import would cycle.
    from ai_dotfiles.core.codex_layout import project_layout
    from ai_dotfiles.core.codex_targets import iter_codex_pairs, iter_codex_rule_plans

    if (
        element.type is ElementType.RULE
        and not resolve_source_path(element, catalog).is_file()
    ):
        return []

    layout = project_layout(project_root)
    pairs: list[tuple[Path, Path]] = [
        (pair.source, pair.target)
        for pair in iter_codex_pairs(element, layout, catalog)
    ]
    for plan in iter_codex_rule_plans(element, layout, catalog):
        pairs.extend((plan.source, target) for target in plan.agents_md_paths)
    return pairs


def _dsh_source_target_pairs(
    source: Path, element_type: ElementType, layout: DshLayout
) -> list[tuple[Path, Path]]:
    """Resolve native DSH contributions without approximating rule activation."""
    from ai_dotfiles.core.frontmatter import parse_frontmatter
    from ai_dotfiles.core.rule_classify import RuleClass, classify_rule

    if element_type is ElementType.SKILL:
        return [(source, layout.skills_dir / source.name)]
    if element_type is ElementType.AGENT:
        return [(source, layout.config_path)]
    if element_type is ElementType.RULE:
        if not source.is_file():
            return []
        try:
            metadata = parse_frontmatter(source.read_text(encoding="utf-8"))
            # Codex may demote glob paths or classify paths + always_on as
            # unconditional. DSH must preserve the original activation gap.
            if metadata.get("paths"):
                return []
            rule_class = classify_rule(source)
        except OSError as exc:
            raise ElementError(f"Cannot read DSH rule {source}: {exc}") from exc
        if rule_class is RuleClass.ALWAYS_ON:
            return [(source, layout.root_agents_md)]
        # Description-only Claude rules remain unconditional through the
        # DSH literal bridge, without changing Codex's synthetic-skill policy.
        return [(source, layout.config_path)]
    raise ElementError(  # pragma: no cover - exhaustive
        f"Unsupported DSH element type: {element_type!r}"
    )


def _dsh_target_pairs(
    element: Element, layout: DshLayout, catalog: Path
) -> list[tuple[Path, Path]]:
    """Return native member destinations for either DSH scope.

    Agent and literal rule rows share the aggregate configuration snapshot;
    these pairs describe contributions, not file-copy operations. Hooks and
    native fragments are collected separately with their origin resources.
    Path-scoped rules yield no pair; later rendering reports the native gap.
    """
    if element.type is not ElementType.DOMAIN:
        return _dsh_source_target_pairs(
            resolve_source_path(element, catalog), element.type, layout
        )

    pairs: list[tuple[Path, Path]] = []
    domain_root = catalog / element.name
    for subdir, member_type in (
        ("skills", ElementType.SKILL),
        ("agents", ElementType.AGENT),
        ("rules", ElementType.RULE),
    ):
        source_dir = domain_root / subdir
        if not source_dir.is_dir():
            continue
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _DOMAIN_SKIP_FILES or entry.name.startswith("."):
                continue
            if member_type is ElementType.SKILL:
                if not entry.is_dir():
                    continue
            elif entry.suffix != ".md" or not entry.is_file():
                continue
            pairs.extend(_dsh_source_target_pairs(entry, member_type, layout))
    return pairs


def resolve_target_paths(
    element: Element,
    config_root: Path | DshLayout,
    catalog: Path,
    target: Target | None = None,
) -> list[tuple[Path, Path]]:
    """Return ``(source, target)`` pairs to materialise ``element`` for ``target``.

    ``target`` defaults to :data:`Target.CLAUDE`; the Claude resolution is
    byte-identical to the pre-multi-target behaviour. For Claude,
    ``config_root`` is the ``.claude`` directory; for Codex it is the
    project root (Codex spreads skills and agents across two distinct
    sub-trees). DSH accepts a project root or an explicit
    :class:`~ai_dotfiles.core.dsh_layout.DshLayout` for project/user scope.

    For :data:`ElementType.DOMAIN`, the domain is expanded into its member
    elements. For a standalone skill/agent a single pair is returned. A
    Codex rule dispatches by :class:`~ai_dotfiles.core.rule_classify.RuleClass`
    and may yield several pairs (one ``AGENTS.md`` per ``paths:`` entry)
    or one synthetic-skill pair. DSH rules with non-empty source ``paths``
    yield no pair; unconditional rules contribute to ``AGENTS.md`` or the
    owned literal bridge configuration. Unsupported explicit targets raise
    :class:`ElementError` instead of falling through to another target.
    """
    # Imported lazily to avoid a module-level import cycle (``targets``
    # imports ``ElementType`` from this module).
    from ai_dotfiles.core.targets import Target as _Target

    effective = _Target.CLAUDE if target is None else target
    if effective is _Target.DSH:
        from ai_dotfiles.core.dsh_layout import DshLayout, project_layout

        layout = (
            config_root
            if isinstance(config_root, DshLayout)
            else project_layout(config_root)
        )
        return _dsh_target_pairs(element, layout, catalog)
    if not isinstance(config_root, Path):
        raise ElementError("A DSH layout requires the DSH target.")
    if effective is _Target.CLAUDE:
        return _claude_target_pairs(element, config_root, catalog)
    if effective is _Target.CODEX:
        return _codex_target_pairs(element, config_root, catalog)
    raise ElementError(f"Unsupported target: {effective!r}")


def validate_element_exists(element: Element, catalog: Path) -> None:
    """Raise :class:`ElementError` if ``element`` is not present in ``catalog``."""
    source = resolve_source_path(element, catalog)
    if not source.exists():
        raise ElementError(
            f"Element {element.raw!r} not found in catalog: {source} does not exist."
        )
