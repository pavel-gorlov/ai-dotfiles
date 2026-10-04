"""Plan shared project Markdown ownership before any lifecycle mutation.

Catalog contributions follow each enabled target's existing dispatch. Codex
path-scoped blocks remain unchanged; DSH accepts only original no-path rules
and sends unconditional description rules to its private literal bridge.

Both local registries share one narrow protection contract: ``rule_blocks``
is an optional JSON object mapping project-relative ``AGENTS.md`` paths to
lists of marker-safe rule names. Other registry fields are intentionally
ignored. Protection persists independently of enabled catalog targets until
the corresponding local migration/reconciliation producer retires the entry.
This module reads only named sources and registries, never scans project trees
or writes files. Consumers must compute this plan before removal or pruning.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ai_dotfiles.core.agents_md import AGENTS_FILENAME, block_markers, rule_name_of
from ai_dotfiles.core.codex_layout import project_layout as codex_project_layout
from ai_dotfiles.core.codex_local_registry import registry_path
from ai_dotfiles.core.codex_render import split_body
from ai_dotfiles.core.codex_targets import iter_codex_rule_plans
from ai_dotfiles.core.dsh_layout import project_layout as dsh_project_layout
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    resolve_source_path,
    resolve_target_paths,
)
from ai_dotfiles.core.errors import ConfigError, ElementError
from ai_dotfiles.core.rule_classify import GLOB_METACHARS
from ai_dotfiles.core.targets import Target

__all__ = [
    "ProjectInstructionPlan",
    "SharedRuleBlock",
    "project_instruction_plan",
]


@dataclass(frozen=True)
class SharedRuleBlock:
    """One marker span, coalescing identical catalog source contributions.

    ``body`` uses the existing Codex body/hash contract. Different sources
    with the same name and body share one block; conflicting bodies fail
    rather than silently selecting whichever target installs last.
    """

    path: Path
    name: str
    body: str
    sources: tuple[Path, ...]
    contributors: frozenset[Target]


@dataclass(frozen=True)
class ProjectInstructionPlan:
    """Catalog wanted blocks plus local protection for a project manifest.

    Recompute after a manifest change, including an empty element or target
    list. ``keep_blocks`` is the union destructive consumers must respect.
    Shared Markdown paths and ``project_root`` are canonical filesystem paths,
    so project-root aliases and in-project directory symlinks share one key.
    This does not change the DSH layout's lexical native-discovery bindings.
    Local registry records protect existing blocks; they are not sufficient
    to regenerate a body, which remains the local reconcile owner's job.
    """

    project_root: Path
    blocks: tuple[SharedRuleBlock, ...]
    protected_blocks: dict[Path, set[str]]
    dsh_literal_rules: tuple[Path, ...]

    @property
    def wanted_blocks(self) -> dict[Path, set[str]]:
        """Return catalog marker names wanted at each project path."""
        wanted: dict[Path, set[str]] = {}
        for block in self.blocks:
            wanted.setdefault(block.path, set()).add(block.name)
        return wanted

    @property
    def keep_blocks(self) -> dict[Path, set[str]]:
        """Return catalog and both local registries' protected marker union."""
        keep = self.wanted_blocks
        for path, names in self.protected_blocks.items():
            keep.setdefault(path, set()).update(names)
        return keep

    def removable_names(self, path: Path, existing_names: Iterable[str]) -> set[str]:
        """Return only names absent from every surviving contributor."""
        path = _project_block_path(path, self.project_root)
        return set(existing_names) - self.keep_blocks.get(path, set())


def _project_block_path(path: Path, root: Path) -> Path:
    """Canonicalize one shared key after validating filesystem containment."""
    resolved = path.resolve()
    if (
        path.name != AGENTS_FILENAME
        or ".." in path.parts
        or not resolved.is_relative_to(root)
        or any(ch in GLOB_METACHARS for part in path.parts for ch in part)
    ):
        raise ElementError(f"Shared instruction path is outside project: {path}")
    if path.is_symlink():
        raise ElementError(f"Refusing symlinked shared AGENTS.md target: {path}")
    return resolved


def _local_protected_blocks(path: Path, root: Path) -> dict[Path, set[str]]:
    """Read only the common rule_blocks contract, refusing unsafe records."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read local rule registry {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rule_blocks", {}), dict):
        raise ConfigError(f"Local registry {path} needs a rule_blocks object")
    blocks: dict[Path, set[str]] = {}
    for relative, names in data.get("rule_blocks", {}).items():
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or not isinstance(names, list)
            or not all(isinstance(name, str) for name in names)
        ):
            raise ConfigError(f"Invalid rule_blocks entry in {path}: {relative!r}")
        try:
            target = _project_block_path(root / relative, root)
            for name in names:
                block_markers(name)
        except ElementError as exc:
            raise ConfigError(f"Invalid rule_blocks entry in {path}: {exc}") from exc
        if names:
            blocks.setdefault(target, set()).update(names)
    return blocks


def _rule_sources(element: Element, catalog: Path) -> Iterator[Path]:
    """Enumerate only a selected rule or a selected domain's rule directory."""
    if element.type is ElementType.RULE:
        yield resolve_source_path(element, catalog)
    elif element.type is ElementType.DOMAIN:
        directory = catalog / element.name / "rules"
        if directory.is_dir():
            for source in sorted(directory.iterdir()):
                if (
                    source.suffix == ".md"
                    and source.name != "README.md"
                    and not source.name.startswith(".")
                    and source.is_file()
                ):
                    yield source


def project_instruction_plan(
    elements: Sequence[Element],
    targets: Iterable[Target],
    project_root: Path,
    catalog: Path,
) -> ProjectInstructionPlan:
    """Collect wanted/protected project blocks without performing any writes.

    Targets are the caller's resolved manifest targets; no default or unknown
    target interpretation happens here. Source/path collisions are validated
    before returning a plan, so a destructive caller cannot act on a partial
    union. DSH literal rules are source paths for its private bridge consumer.
    """
    manifest_root = project_root.absolute()
    root = manifest_root.resolve()
    enabled = set(targets)
    codex_layout = codex_project_layout(root)
    dsh_layout = dsh_project_layout(manifest_root)
    protected: dict[Path, set[str]] = {}
    for registry in (registry_path(root), dsh_layout.local_registry_path):
        for path, names in _local_protected_blocks(registry, root).items():
            protected.setdefault(path, set()).update(names)

    blocks: dict[tuple[Path, str], SharedRuleBlock] = {}
    literals: list[Path] = []

    def add_block(source: Path, path: Path, target: Target) -> None:
        path = _project_block_path(path, root)
        name = rule_name_of(source)
        try:
            body = split_body(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise ElementError(
                f"Cannot read shared instruction {source}: {exc}"
            ) from exc
        key = path, name
        previous = blocks.get(key)
        if previous is None:
            blocks[key] = SharedRuleBlock(
                path, name, body, (source,), frozenset({target})
            )
        elif previous.body != body:
            raise ElementError(
                f"Conflicting shared rule {name!r} at {path}: "
                f"{previous.sources[0]} and {source}"
            )
        else:
            sources = previous.sources
            if source not in sources:
                sources += (source,)
            blocks[key] = replace(
                previous, sources=sources, contributors=previous.contributors | {target}
            )

    for element in elements:
        if Target.CODEX in enabled:
            for plan in iter_codex_rule_plans(element, codex_layout, catalog):
                for path in plan.agents_md_paths:
                    add_block(plan.source, path, Target.CODEX)
        if Target.DSH in enabled:
            sources = set(_rule_sources(element, catalog))
            if not sources:
                continue
            for source, path in resolve_target_paths(
                element, dsh_layout, catalog, Target.DSH
            ):
                if source not in sources:
                    continue
                if path == dsh_layout.root_agents_md:
                    add_block(source, path, Target.DSH)
                elif path == dsh_layout.config_path and source not in literals:
                    literals.append(source)

    return ProjectInstructionPlan(
        root, tuple(blocks.values()), protected, tuple(literals)
    )
