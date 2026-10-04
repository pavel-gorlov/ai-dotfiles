"""Project-local source identities and bounded DSH retirement provenance.

The registry is a record, never an activation snapshot. Consumers rediscover and
render original files; stored values must not be passed to the native launcher.
Retired sources/blocks remain recorded until a lifecycle consumer verifies and
retires their exact outputs. Shared rule protection uses the existing schema.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from ai_dotfiles.core.agents_md import block_markers
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.errors import ConfigError, ElementError, LinkError
from ai_dotfiles.core.rule_classify import GLOB_METACHARS

DSH_LOCAL_SCHEMA_VERSION = 1
DSH_LOCAL_GENERATOR_VERSION = 1
_SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class DshLocalRegistry:
    """Source-keyed references to the same layout's exact installer inventory.

    outputs/resources/contributions retain custody pending retirement; desired_*
    describes the latest source. Link text/tree modes/digests remain authoritative
    in provenance.json and must be verified there before any deletion.
    """

    sources: dict[str, dict[str, object]] = field(default_factory=dict)
    rule_blocks: dict[str, list[str]] = field(default_factory=dict)

    def snapshot(self) -> dict[str, object]:
        """Return deterministic JSON data, without reading/writing activation."""
        return {
            "managed_by": "ai-dotfiles",
            "target": "dsh",
            "schema_version": DSH_LOCAL_SCHEMA_VERSION,
            "generator": DSH_LOCAL_GENERATOR_VERSION,
            "sources": deepcopy(self.sources),
            "rule_blocks": deepcopy(self.rule_blocks),
        }


def guard_local_path(
    project_root: Path, path: Path, *, destination: bool = False, tree: bool = False
) -> None:
    """Reject traversal/outside links before reads or writes below the project.

    Outer aliases above the explicitly supplied root are retained. Local internal
    links are allowed; managed destinations/parents must never be symlinks.
    Whole local bundles are checked recursively before an installer follows links.
    """
    root, candidate = project_root.absolute(), path.absolute()
    if ".." in candidate.parts or not candidate.is_relative_to(root):
        raise LinkError(f"Local DSH path is outside project: {path}")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise LinkError(f"Local DSH path resolves outside project: {path}")
    if destination:
        for part in (candidate, *candidate.parents):
            if part.is_relative_to(root) and part.is_symlink():
                raise LinkError(f"Refusing symlinked local DSH destination: {part}")
            if (
                part != candidate
                and part.is_relative_to(root)
                and part.exists()
                and not part.is_dir()
            ):
                raise LinkError(f"Local DSH parent is not a directory: {part}")
    if tree and candidate.is_dir():
        visited: set[Path] = set()

        def visit(directory: Path) -> None:
            canonical = directory.resolve()
            if canonical in visited:
                raise LinkError(f"Cyclic local DSH resource: {directory}")
            visited.add(canonical)
            for child in directory.iterdir():
                guard_local_path(root, child)
                if child.is_dir():
                    visit(child)
            visited.remove(canonical)

        visit(candidate)


def _relative(value: object, root: Path, *, check_source: bool = True) -> Path:
    if not isinstance(value, str):
        raise ConfigError(f"Invalid local DSH path: {value!r}")
    path = Path(value)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ConfigError(f"Unsafe local DSH relative path: {value!r}")
    if check_source:
        guard_local_path(root, root / path)
    return path


def validate_dsh_local_registry(project_root: Path, registry: DshLocalRegistry) -> None:
    """Validate all recorded paths and metadata before any materialization."""
    layout = project_layout(project_root)
    guard_local_path(project_root, layout.local_registry_path, destination=True)
    for key, record in registry.sources.items():
        source = _relative(key, project_root)
        if not (source.parts[0] == ".claude" or source.as_posix() == ".mcp.json"):
            raise ConfigError(f"Nonlocal DSH source record: {key}")
        if (
            record.get("source") != key
            or not isinstance(record.get("source_sha256"), str)
            or not _SHA.fullmatch(cast(str, record["source_sha256"]))
            or type(record.get("generator")) is not int
            or cast(int, record["generator"]) < 1
            or record.get("classification") not in ("MECHANICAL", "REFACTOR", "MANUAL")
            or record.get("status") not in ("READY", "DEFERRED", "MANUAL", "HELD")
            or record.get("kind")
            not in ("skill", "agent", "rule", "command", "settings", "hooks", "mcp")
            or not isinstance(record.get("element"), str)
            or not record["element"]
        ):
            raise ConfigError(f"Invalid local DSH source metadata: {key}")
        for field_name in ("outputs", "resources"):
            entries = record.get(field_name)
            if not isinstance(entries, list):
                raise ConfigError(f"Invalid local DSH {field_name}: {key}")
            for entry in entries:
                relative = _relative(entry, layout.dsh_dir, check_source=False)
                output = layout.dsh_dir / relative
                if (
                    output == layout.local_registry_path
                    or output == layout.provenance_path
                    or not any(
                        output != root and output.is_relative_to(root)
                        for root in layout.owned_roots
                    )
                ):
                    raise ConfigError(f"Unowned local DSH output path: {entry}")
                # Output links are valid, symlinked parents are not.
                guard_local_path(project_root, output.parent, destination=True)
        if not set(cast(list[str], record["resources"])).issubset(
            cast(list[str], record["outputs"])
        ):
            raise ConfigError(f"Unrecorded local DSH resource: {key}")
        desired = record.get("desired_outputs")
        if not isinstance(desired, list) or not all(
            isinstance(item, str) and item in cast(list[str], record["outputs"])
            for item in desired
        ):
            raise ConfigError(f"Invalid local DSH desired outputs: {key}")
        provenance = record.get("provenance")
        if not isinstance(provenance, list) or not all(
            isinstance(part, dict)
            and part.get("source") == str(project_root / source)
            and part.get("source_sha256") == record["source_sha256"]
            and part.get("origin") == "local"
            and part.get("element") == record["element"]
            and type(part.get("generator")) is int
            and part["generator"] >= 1
            for part in provenance
        ):
            raise ConfigError(f"Invalid local DSH original provenance: {key}")
        generators = record.get("output_generators")
        if (
            not isinstance(generators, dict)
            or set(generators) != set(cast(list[str], record["outputs"]))
            or not all(
                isinstance(versions, dict)
                and versions
                and all(
                    isinstance(name, str) and type(version) is int and version >= 1
                    for name, version in versions.items()
                )
                for versions in generators.values()
            )
        ):
            raise ConfigError(f"Invalid local DSH output generator provenance: {key}")
        contributions = record.get("contributions")
        if not isinstance(contributions, list) or not all(
            isinstance(name, str) and bool(name) for name in contributions
        ):
            raise ConfigError(f"Invalid local DSH contributions: {key}")
        desired_contributions = record.get("desired_contributions")
        if not isinstance(desired_contributions, list) or not all(
            isinstance(item, str) and item in contributions
            for item in desired_contributions
        ):
            raise ConfigError(f"Invalid local DSH desired contributions: {key}")
        guards = record.get("guards")
        if not isinstance(guards, list):
            raise ConfigError(f"Invalid local DSH guards: {key}")
        for guard in guards:
            if not isinstance(guard, dict):
                raise ConfigError(f"Invalid local DSH guard: {key}")
            _relative(guard.get("source"), project_root)
            digest = guard.get("source_sha256")
            if digest is not None and (
                not isinstance(digest, str) or not _SHA.fullmatch(digest)
            ):
                raise ConfigError(f"Invalid local DSH guard digest: {key}")
    for key, names in registry.rule_blocks.items():
        relative = _relative(key, project_root)
        if (
            relative.name != "AGENTS.md"
            or not isinstance(names, list)
            or any(char in GLOB_METACHARS for part in relative.parts for char in part)
        ):
            raise ConfigError(f"Invalid local DSH rule_blocks: {key}")
        guard_local_path(project_root, project_root / relative, destination=True)
        for name in names:
            if not isinstance(name, str):
                raise ConfigError(f"Invalid local DSH rule name: {name!r}")
            try:
                block_markers(name)
            except ElementError as exc:
                raise ConfigError(f"Invalid local DSH rule name: {name!r}") from exc
    try:
        json.dumps(registry.snapshot(), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid local DSH JSON data: {exc}") from exc


def load_dsh_local_registry(project_root: Path) -> DshLocalRegistry:
    """Read only the project sidecar; refuse foreign or unsafe ownership."""
    path = project_layout(project_root).local_registry_path
    guard_local_path(project_root, path, destination=True)
    if not path.exists():
        return DshLocalRegistry()
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read local DSH registry {path}: {exc}") from exc
    if (
        not isinstance(data, dict)
        or data.get("managed_by") != "ai-dotfiles"
        or data.get("target") != "dsh"
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != DSH_LOCAL_SCHEMA_VERSION
        or type(data.get("generator")) is not int
        or not isinstance(data.get("sources"), dict)
        or not all(
            isinstance(key, str) and isinstance(value, dict)
            for key, value in data["sources"].items()
        )
        or not isinstance(data.get("rule_blocks"), dict)
    ):
        raise ConfigError(f"Foreign/invalid local DSH registry: {path}")
    registry = DshLocalRegistry(data["sources"], data["rule_blocks"])
    validate_dsh_local_registry(project_root, registry)
    return registry


def save_dsh_local_registry(project_root: Path, registry: DshLocalRegistry) -> bool:
    """Write validated ownership only; return whether bytes changed."""
    load_dsh_local_registry(project_root)
    validate_dsh_local_registry(project_root, registry)
    path = project_layout(project_root).local_registry_path
    payload = (
        json.dumps(registry.snapshot(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode()
    if path.is_file() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return True
