"""Bounded DSH materialization, with read-only planning and exact ownership.

The registry owns individual outputs, never every descendant of an owned root.
Every destination is preflighted before the first write. Copied trees may be
refreshed only while their remaining entries match the recorded inventory;
user additions/edits and foreign symlinks are collisions. A link's ownership is
its recorded link text, independently of changes in the catalog bundle.

These APIs produce contributions, not a merged native composition or runtime
readiness. The host still selects the effective scope, boots native Loader and
awaits the audit before exposing a surface. Deferred sources can be retried
with native metadata in ``collect_dsh_elements`` or supplied as READY renderer
results to ``plan_dsh_install``. No parser/runtime is installed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, TypedDict, cast

from ai_dotfiles.core import agents_md, manifest
from ai_dotfiles.core.codex_local_registry import load_local_registry, registry_path
from ai_dotfiles.core.codex_render import split_body
from ai_dotfiles.core.dsh_admission import (
    admitted_permissions,
    require_admission,
    skipped_diagnostics,
)
from ai_dotfiles.core.dsh_audit import (
    DSH_AUDIT_GENERATOR_VERSION,
    DSH_AUDIT_ROW_ID,
    DSH_BRIDGE_GENERATOR_VERSION,
    DSH_BRIDGE_ROW_ID,
    DshAuditRequirements,
    DshBridgeConfig,
    audit_module_text,
    bridge_audit_requirements,
    bridge_module_text,
    build_bridge_config,
)
from ai_dotfiles.core.dsh_layout import DshLayout
from ai_dotfiles.core.dsh_local_registry import load_dsh_local_registry
from ai_dotfiles.core.dsh_native import native_frontmatter_failure
from ai_dotfiles.core.dsh_permissions import DshPermissionPolicy
from ai_dotfiles.core.dsh_render import (
    DshAgentPayload,
    DshDiagnostic,
    DshProvenance,
    DshRenderResult,
    DshRulePayload,
    DshSkillPayload,
    render_agent,
    render_rule,
    validate_skill,
)
from ai_dotfiles.core.elements import Element, ElementType, resolve_source_path
from ai_dotfiles.core.errors import ConfigError, ElementError, LinkError, SourceError
from ai_dotfiles.core.fs_copy import copy_tree_into
from ai_dotfiles.core.shared_instructions import (
    ProjectInstructionPlan,
    project_instruction_plan,
)
from ai_dotfiles.core.symlinks import safe_symlink
from ai_dotfiles.core.targets import Target

DSH_INSTALL_GENERATOR_VERSION = 3
DSH_OWNERSHIP_SCHEMA_VERSION = 1
DSH_SHARED_CUSTODY_GENERATOR_VERSION = 1
InstallMode = Literal["link", "copy"]
_EMPTY_PERMISSIONS = DshPermissionPolicy()
TreeInventory = dict[str, dict[str, str | int]]
RenderResult = (
    DshRenderResult[DshSkillPayload]
    | DshRenderResult[DshAgentPayload]
    | DshRenderResult[DshRulePayload]
)


class DshOwnershipRecord(TypedDict):
    """One exact output; tree entries include bytes, kind and POSIX mode.

    Paths are relative to dsh_dir; tree keys are relative to that output.
    source_tree_sha256 covers the complete source, including support resources.
    Link text is separate from source inventory so catalog drift is refreshable.
    """

    mode: Literal["link", "copy", "generated"]
    source: str | None
    source_tree_sha256: str
    source_inventory: TreeInventory
    output_inventory: TreeInventory
    provenance: list[dict[str, str | int]]
    generators: dict[str, int]


@dataclass(frozen=True)
class DshResource:
    """An origin-bound complete resource under resources_dir.

    relative_path is a safe relative path within resources_dir. The source may
    be a file or a complete directory. Copy is self-contained and retains modes;
    link is explicit. Domain collectors bind paths against this installed root.
    """

    source: Path
    relative_path: Path
    provenance: DshProvenance
    mode: InstallMode = "copy"


@dataclass(frozen=True)
class DshOutput:
    """A planned bundle/link or generated file, with no write side effects."""

    path: Path
    mode: Literal["link", "copy", "generated"]
    provenance: tuple[DshProvenance, ...]
    generators: dict[str, int]
    source: Path | None = None
    source_inventory: TreeInventory = field(default_factory=dict)
    content: bytes | None = None


@dataclass(frozen=True)
class DshInstallPlan:
    """Inspectable sources, outputs and READY contributions for one scope.

    Nonready results retain diagnostics/provenance and cannot enter native rows
    or shared blocks. permissions retains blocked policies; bridge_config then
    refuses activation instead of silently producing an empty restriction set.
    No property implies that a native provider/plugin is available or loaded.
    """

    layout: DshLayout
    skills: tuple[DshRenderResult[DshSkillPayload], ...]
    agents: tuple[DshRenderResult[DshAgentPayload], ...]
    rules: tuple[DshRenderResult[DshRulePayload], ...]
    resources: tuple[DshResource, ...]
    outputs: tuple[DshOutput, ...]
    permissions: DshPermissionPolicy
    instructions: ProjectInstructionPlan | None
    permission_modes: tuple[tuple[Path, manifest.DshPermissionMode, str], ...] = ()
    strict: bool = False
    activation_diagnostics: tuple[DshDiagnostic, ...] = ()
    rejected_skill_sources: tuple[Path, ...] = ()
    rejected_skill_paths: tuple[Path, ...] = ()
    source_errors: tuple[tuple[Path, DshDiagnostic], ...] = ()

    @property
    def desired_output_keys(self) -> frozenset[str]:
        """Current wanted entries; old/nonready native outputs are not included."""
        return frozenset(
            _output_key(self.layout, output.path) for output in self.outputs
        )

    @property
    def current_source_ids(self) -> frozenset[str]:
        """Current READY/DEFERRED/MANUAL identities for retirement comparison."""
        return frozenset(
            _source_id(result.provenance)
            for result in (*self.skills, *self.agents, *self.rules)
        )

    @property
    def diagnostics(self) -> tuple[DshDiagnostic, ...]:
        return (
            tuple(
                item
                for result in (*self.skills, *self.agents, *self.rules)
                for item in result.diagnostics
            )
            + self.permissions.diagnostics
            + self.activation_diagnostics
            + tuple(item for _, item in self.source_errors)
        )

    @property
    def skipped(self) -> tuple[DshDiagnostic, ...]:
        return skipped_diagnostics(self.diagnostics)

    @property
    def partial(self) -> bool:
        return bool(self.skipped)

    def require_activatable(self, *, strict: bool = False) -> None:
        require_admission(
            self.diagnostics,
            strict=strict or self.strict,
            context="Cannot activate DSH install",
        )

    @property
    def ready_agents(self) -> tuple[DshRenderResult[DshAgentPayload], ...]:
        return tuple(result for result in self.agents if result.status == "READY")

    @property
    def literal_rules(self) -> tuple[DshRenderResult[DshRulePayload], ...]:
        return tuple(
            result
            for result in self.rules
            if result.status == "READY"
            and result.payload is not None
            and result.payload.activation == "literal"
        )

    @property
    def shared_rules(self) -> tuple[DshRenderResult[DshRulePayload], ...]:
        return tuple(
            result
            for result in self.rules
            if result.status == "READY"
            and result.payload is not None
            and result.payload.activation == "shared"
        )

    def bridge_config(self) -> DshBridgeConfig:
        """Return scope contributions; blocked permissions raise ConfigError."""
        return build_bridge_config(
            self.ready_agents,
            self.literal_rules,
            permissions=admitted_permissions(self.permissions, strict=self.strict),
        )

    def audit_requirements(self) -> DshAuditRequirements:
        """Return producer requirements to union into the selected native scope."""
        return bridge_audit_requirements(self.bridge_config())

    def native_rows(self) -> list[dict[str, object]]:
        """Return source rows; callers merge precedence before native insertion.

        The aggregate collector rebuilds bridge/audit configs after combining
        scopes and adds skill/hook/MCP/provider requirements. Never concatenate
        these per-scope bridge rows into an effective composition.
        """
        rows: list[dict[str, object]] = []
        for result in self.ready_agents:
            assert result.payload is not None
            rows.append(deepcopy(dict(result.payload.row)))
        rows.extend(
            (
                {
                    "id": DSH_BRIDGE_ROW_ID,
                    "name": self.layout.bridge_path.absolute().as_uri(),
                    "config": self.bridge_config(),
                },
                {
                    "id": DSH_AUDIT_ROW_ID,
                    "name": audit_path(self.layout).absolute().as_uri(),
                    "config": self.audit_requirements().as_dict(),
                },
            )
        )
        return rows


@dataclass(frozen=True)
class DshInventory:
    """Registry inventory, safe for later status/reconcile and bounded prune.

    Consumers must preflight entries before deletion; a recorded tree root is
    not permission to delete unrecorded descendants. rule_blocks is the common
    shared Markdown protection contract. source_records also retains nonready
    sources; output records retain retired contributions until lifecycle owners
    deliberately remove them. No HOME/project recursive scan is performed.
    """

    records: dict[str, DshOwnershipRecord] = field(default_factory=dict)
    source_records: dict[str, dict[str, object]] = field(default_factory=dict)
    rule_blocks: dict[str, list[str]] = field(default_factory=dict)
    shared_rule_records: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class DshInstallResult:
    changed_paths: tuple[Path, ...]
    inventory: DshInventory
    plan: DshInstallPlan

    @property
    def retired_output_keys(self) -> tuple[str, ...]:
        """Owned outputs absent from this plan, still awaiting lifecycle retirement.

        In particular READY -> DEFERRED/MANUAL leaves an old native skill here.
        Reconcile/launch must retire it or refuse stale activation; omission from
        the new contributions does not establish safe native discovery. Consumers
        combine catalog/local desired sets before retiring any shared inventory.
        """
        return tuple(
            sorted(set(self.inventory.records) - self.plan.desired_output_keys)
        )


def audit_path(layout: DshLayout) -> Path:
    """The owned audit module (native profiles/package.json remain untouched)."""
    return layout.owned_dir / "audit.mjs"


def _json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative(path: Path) -> bool:
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def _guard(path: Path, anchor: Path) -> None:
    """Prove containment and reject managed symlink/file parents before writes.

    Outer aliases such as macOS /tmp are part of the explicitly selected root,
    not managed paths. Preserve their lexical native spelling; only parents at
    or below the anchor can redirect writes outside that configured boundary.
    """
    path, anchor = path.absolute(), anchor.absolute()
    if ".." in path.parts or not path.is_relative_to(anchor):
        raise LinkError(f"DSH destination is outside its explicit root: {path}")
    for parent in reversed(path.parents):
        if parent.is_relative_to(anchor):
            if parent.is_symlink():
                raise LinkError(f"Refusing symlinked DSH parent: {parent}")
            if parent.exists() and not parent.is_dir():
                raise LinkError(f"DSH parent is not a directory: {parent}")


def _anchor(layout: DshLayout) -> Path:
    return layout.project_root if layout.project_root is not None else layout.dsh_dir


def _guard_local_registries(layout: DshLayout) -> None:
    if layout.project_root is None:
        return
    for path in (layout.local_registry_path, registry_path(layout.project_root)):
        _guard(path, layout.project_root)
        if path.is_symlink():
            raise LinkError(f"Refusing symlinked DSH/shared local registry: {path}")


def _verify_shared_block(text: str, name: str) -> None:
    start, end = agents_md.block_markers(name)
    span = text[text.index(start) : text.index(end) + len(end)]
    match = re.fullmatch(
        re.escape(start)
        + r"\r?\n<!-- ai-dotfiles:rule:"
        + re.escape(name)
        + r" sha256:([0-9a-f]{64}) -->\r?\n(.*?)\r?\n"
        + re.escape(end),
        span,
        re.DOTALL,
    )
    if (
        match is None
        or _sha(match[2].replace("\r\n", "\n").strip().encode("utf-8")) != match[1]
    ):
        raise LinkError(f"Foreign/modified shared DSH block: {name}")


def _clear_owned_output(path: Path) -> None:
    # Called only after the entire plan passed precise per-entry verification.
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _output_key(layout: DshLayout, path: Path) -> str:
    _guard(path, _anchor(layout))
    absolute = path.absolute()
    if not any(
        absolute != root.absolute() and absolute.is_relative_to(root.absolute())
        for root in layout.owned_roots
    ):
        raise LinkError(f"DSH output is outside owned roots: {path}")
    if absolute == layout.provenance_path.absolute():
        raise LinkError("DSH provenance.json cannot also be an output")
    return str(absolute.relative_to(layout.dsh_dir.absolute()))


def _inventory(path: Path, *, follow_links: bool) -> TreeInventory:
    """Snapshot one named tree, including empty directories and executable bits."""
    entries: TreeInventory = {}

    def visit(current: Path, relative: str, ancestors: frozenset[Path]) -> None:
        if current.is_symlink() and not follow_links:
            entries[relative] = {"kind": "link", "target": os.readlink(current)}
            return
        info = current.stat() if follow_links else current.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISREG(info.st_mode):
            entries[relative] = {
                "kind": "file",
                "mode": mode,
                "sha256": _sha(current.read_bytes()),
            }
        elif stat.S_ISDIR(info.st_mode):
            canonical = current.resolve()
            if canonical in ancestors:
                raise LinkError(f"Cyclic DSH resource tree: {current}")
            entries[relative] = {"kind": "directory", "mode": mode}
            for child in sorted(current.iterdir()):
                child_key = (
                    child.name if relative == "." else f"{relative}/{child.name}"
                )
                visit(child, child_key, ancestors | {canonical})
        else:
            raise LinkError(f"Unsupported DSH resource file type: {current}")

    try:
        visit(path, ".", frozenset())
    except OSError as exc:
        raise LinkError(f"Cannot inventory DSH resource {path}: {exc}") from exc
    return entries


def _source_record[T](result: DshRenderResult[T]) -> dict[str, object]:
    try:
        source_text = result.provenance.source.read_bytes()
        decoded = source_text.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise LinkError(
            f"Cannot read DSH contribution {result.provenance.source}: {exc}"
        ) from exc
    if _sha(source_text) != result.provenance.source_sha256:
        raise LinkError(
            f"DSH source changed after rendering: {result.provenance.source}"
        )
    payload = result.payload
    data: dict[str, object] = {
        "managed_by": "ai-dotfiles",
        "target": "dsh",
        "generator": DSH_INSTALL_GENERATOR_VERSION,
        "provenance": result.provenance.as_dict(),
        "status": result.status,
        "diagnostics": [asdict(item) for item in result.diagnostics],
        "source_text": decoded,
    }
    if result.status == "READY" and payload is not None:
        if isinstance(payload, DshAgentPayload):
            data["row"] = payload.row
            data["bridge"] = payload.bridge_data(result.provenance)
            data["required_tools"] = list(payload.required_tools)
        elif isinstance(payload, DshRulePayload):
            data["activation"] = payload.activation
            data["name"] = payload.name
            data["body"] = payload.body
            if payload.activation == "literal":
                data["bridge"] = payload.bridge_data(result.provenance)
        elif isinstance(payload, DshSkillPayload):
            data["name"] = payload.name
            data["invocation"] = payload.invocation
    return data


def _source_id(provenance: DshProvenance) -> str:
    return _sha(_json([provenance.origin, provenance.element, str(provenance.source)]))


def _validate_shared_custody(key: str, value: object) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or type(value.get("schema_version")) is not int
        or value.get("generator") != DSH_SHARED_CUSTODY_GENERATOR_VERSION
        or type(value.get("generator")) is not int
        or not isinstance(value.get("source_record"), dict)
    ):
        raise ConfigError(f"Invalid DSH historical rule custody: {key}")
    record = cast(dict[str, object], value["source_record"])
    provenance, text, body, name = (
        record.get("provenance"),
        record.get("source_text"),
        record.get("body"),
        record.get("name"),
    )
    if (
        record.get("managed_by") != "ai-dotfiles"
        or record.get("target") != "dsh"
        or record.get("status") != "READY"
        or record.get("activation") != "shared"
        or type(record.get("generator")) is not int
        or not isinstance(provenance, dict)
        or not all(
            isinstance(provenance.get(field), str) and provenance[field]
            for field in ("source", "origin", "element", "source_sha256")
        )
        or type(provenance.get("generator")) is not int
        or not isinstance(text, str)
        or _sha(text.encode()) != provenance.get("source_sha256")
        or not isinstance(body, str)
        or split_body(text.replace("\r\n", "\n").replace("\r", "\n")) != body
        or not isinstance(name, str)
        or key
        != _sha(
            _json([provenance["origin"], provenance["element"], provenance["source"]])
        )
    ):
        raise ConfigError(f"Conflicting DSH historical rule custody: {key}")
    agents_md.block_markers(name)
    return record


def _historical_shared_rules(inventory: DshInventory) -> dict[str, dict[str, object]]:
    return {
        key: _validate_shared_custody(key, value)
        for key, value in inventory.shared_rule_records.items()
    }


def plan_dsh_install(
    layout: DshLayout,
    *,
    skills: Iterable[DshRenderResult[DshSkillPayload]] = (),
    agents: Iterable[DshRenderResult[DshAgentPayload]] = (),
    rules: Iterable[DshRenderResult[DshRulePayload]] = (),
    resources: Iterable[DshResource] = (),
    mode: InstallMode = "link",
    permissions: DshPermissionPolicy = _EMPTY_PERMISSIONS,
    instructions: ProjectInstructionPlan | None = None,
    strict: bool = False,
    source_errors: Iterable[tuple[Path, DshDiagnostic]] = (),
) -> DshInstallPlan:
    """Plan complete native bundles and source contributions without any writes.

    Accept retried READY results from the pinned parser directly. Domain hooks
    and other resources can be supplied by later collectors through DshResource.
    Aggregate config.json/patch.json/hooks.json are deliberately not generated.
    """
    if mode not in ("link", "copy"):
        raise ConfigError(f"Unknown DSH install mode: {mode}")
    skill_results, agent_results, rule_results = (
        tuple(skills),
        tuple(agents),
        tuple(rules),
    )
    resource_results = tuple(resources)
    errors = tuple(source_errors)
    _guard_local_registries(layout)
    if layout.project_root is not None and instructions is None:
        instructions = project_instruction_plan((), (), layout.project_root, Path("."))
    outputs: list[DshOutput] = []
    error_path = layout.resources_dir / "contributions" / "source-errors.json"
    if errors or _output_key(layout, error_path) in read_dsh_inventory(layout).records:
        reporting_source = Path(__file__)
        reporting_provenance = DshProvenance(
            reporting_source,
            "builtin",
            "dsh-source-errors",
            _sha(reporting_source.read_bytes()),
            DSH_INSTALL_GENERATOR_VERSION,
        )
        outputs.append(
            DshOutput(
                error_path,
                "generated",
                (reporting_provenance,),
                {"install": DSH_INSTALL_GENERATOR_VERSION},
                content=_json(
                    {
                        "errors": [
                            {"path": str(path), "diagnostic": asdict(item)}
                            for path, item in errors
                        ]
                    }
                ),
            )
        )
    for result in (*skill_results, *agent_results, *rule_results):
        if result.status == "READY" and (
            result.payload is None or any(item.blocking for item in result.diagnostics)
        ):
            raise ConfigError(f"Invalid READY DSH result: {result.provenance.element}")
        outputs.append(
            DshOutput(
                layout.resources_dir
                / "contributions"
                / f"{_source_id(result.provenance)}.json",
                "generated",
                (result.provenance,),
                {
                    "install": DSH_INSTALL_GENERATOR_VERSION,
                    "render": result.provenance.generator,
                },
                content=_json(_source_record(result)),
            )
        )
    for skill in skill_results:
        if skill.status != "READY":
            continue
        assert skill.payload is not None
        source = skill.payload.directory
        if skill.payload.source.name != "SKILL.md":
            raise ElementError(
                f"DSH catalog skills require a full SKILL.md bundle: {source}"
            )
        outputs.append(
            DshOutput(
                layout.skills_dir / source.name,
                mode,
                (skill.provenance,),
                {
                    "install": DSH_INSTALL_GENERATOR_VERSION,
                    "render": skill.provenance.generator,
                },
                source=source,
                source_inventory=_inventory(source, follow_links=True),
            )
        )
    for resource in resource_results:
        if not _safe_relative(resource.relative_path) or resource.mode not in (
            "link",
            "copy",
        ):
            raise ConfigError(
                f"Unsafe DSH resource path/mode: {resource.relative_path}"
            )
        outputs.append(
            DshOutput(
                layout.resources_dir / resource.relative_path,
                resource.mode,
                (resource.provenance,),
                {
                    "install": DSH_INSTALL_GENERATOR_VERSION,
                    "resource": resource.provenance.generator,
                },
                source=resource.source,
                source_inventory=_inventory(resource.source, follow_links=True),
            )
        )
    for path, text, kind, generator in (
        (
            layout.bridge_path,
            bridge_module_text(),
            "bridge",
            DSH_BRIDGE_GENERATOR_VERSION,
        ),
        (audit_path(layout), audit_module_text(), "audit", DSH_AUDIT_GENERATOR_VERSION),
    ):
        lines = text.splitlines()
        provenance = DshProvenance(
            Path(__file__).parent.parent / "scaffold" / "templates" / f"dsh_{kind}.mjs",
            "builtin",
            f"dsh-{kind}",
            lines[1].removeprefix("// source-sha256: "),
            generator,
        )
        outputs.append(
            DshOutput(
                path,
                "generated",
                (provenance,),
                {kind: generator},
                content=text.encode("utf-8"),
            )
        )
    plan = DshInstallPlan(
        layout,
        skill_results,
        agent_results,
        rule_results,
        resource_results,
        tuple(outputs),
        permissions,
        instructions,
        strict=strict,
        source_errors=errors,
    )
    # Name collisions are errors even if the permission policy is blocked.
    build_bridge_config(plan.ready_agents, plan.literal_rules)
    _validate_output_plan(plan)
    plan.require_activatable()
    return plan


def collect_dsh_elements(
    elements: Sequence[Element],
    layout: DshLayout,
    catalog: Path,
    *,
    mode: InstallMode = "link",
    targets: Iterable[Target] = (Target.DSH,),
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
    permissions: DshPermissionPolicy = _EMPTY_PERMISSIONS,
    strict: bool = False,
) -> DshInstallPlan:
    """Collect selected catalog sources, including unsupported/path rule gaps.

    Original permission sources must be translated before settings merge by the
    caller. native_frontmatter contains pinned native-parser results keyed by
    instruction-file path. Full domain resources keep handlers and sibling files
    available independently of any Claude install, with source-bound paths.
    """
    skills: list[DshRenderResult[DshSkillPayload]] = []
    agents: list[DshRenderResult[DshAgentPayload]] = []
    rules: list[DshRenderResult[DshRulePayload]] = []
    resources: list[DshResource] = []
    source_errors: list[tuple[Path, DshDiagnostic]] = []
    seen: set[tuple[ElementType, Path]] = set()
    seen_domains: set[Path] = set()
    _guard_local_registries(layout)
    metadata = native_frontmatter or {}

    def read_element(
        kind: ElementType, source: Path, origin: str, element: str
    ) -> None:
        key = kind, source.absolute()
        if key in seen:
            return
        seen.add(key)
        if kind is ElementType.SKILL:
            instruction = source / "SKILL.md"
            skills.append(
                validate_skill(
                    instruction,
                    origin=origin,
                    element=element,
                    native_frontmatter=metadata.get(instruction),
                )
            )
        elif kind is ElementType.AGENT:
            agents.append(
                render_agent(
                    source,
                    origin=origin,
                    element=element,
                    native_frontmatter=metadata.get(source),
                )
            )
        else:
            rules.append(
                render_rule(
                    source,
                    origin=origin,
                    element=element,
                    native_frontmatter=metadata.get(source),
                )
            )

    def collect(kind: ElementType, source: Path, origin: str, element: str) -> None:
        try:
            read_element(kind, source, origin, element)
        except SourceError as exc:
            if kind is ElementType.RULE:
                raise
            instruction = source / "SKILL.md" if kind is ElementType.SKILL else source
            source_errors.append(
                (
                    instruction,
                    DshDiagnostic(
                        "SOURCE_UNAVAILABLE", origin, element, "source", str(exc)
                    ),
                )
            )

    for element in elements:
        source = resolve_source_path(element, catalog)
        if element.type is not ElementType.DOMAIN:
            collect(element.type, source, "catalog", element.raw)
            continue
        if source.absolute() in seen_domains:
            continue
        seen_domains.add(source.absolute())
        if not source.is_dir():
            raise ElementError(f"DSH domain source is not a directory: {source}")
        digest = _sha(_json(_inventory(source, follow_links=True)))
        resources.append(
            DshResource(
                source,
                Path("domains") / element.name,
                DshProvenance(source, element.raw, element.raw, digest),
            )
        )
        for subdir, kind in (
            ("skills", ElementType.SKILL),
            ("agents", ElementType.AGENT),
            ("rules", ElementType.RULE),
        ):
            directory = source / subdir
            if not directory.is_dir():
                continue
            for member in sorted(directory.iterdir()):
                if member.name.startswith(".") or member.name == "README.md":
                    continue
                if kind is ElementType.SKILL:
                    if not member.is_dir():
                        continue
                elif member.suffix != ".md" or not member.is_file():
                    continue
                collect(
                    kind, member, element.raw, f"{element.raw}/{subdir}/{member.name}"
                )
    instructions = (
        project_instruction_plan(elements, targets, layout.project_root, catalog)
        if layout.project_root is not None
        else None
    )
    return plan_dsh_install(
        layout,
        skills=(
            native_frontmatter_failure(result, native_frontmatter) for result in skills
        ),
        agents=(
            native_frontmatter_failure(result, native_frontmatter) for result in agents
        ),
        rules=(
            native_frontmatter_failure(result, native_frontmatter) for result in rules
        ),
        resources=resources,
        mode=mode,
        permissions=permissions,
        instructions=instructions,
        strict=strict,
        source_errors=source_errors,
    )


def _validate_output_plan(plan: DshInstallPlan) -> None:
    keys: set[str] = set()
    for output in plan.outputs:
        key = _output_key(plan.layout, output.path)
        if key in keys or any(
            Path(key).is_relative_to(Path(other))
            or Path(other).is_relative_to(Path(key))
            for other in keys
        ):
            raise LinkError(f"Overlapping DSH planned outputs: {output.path}")
        keys.add(key)
    if plan.instructions is not None and (
        plan.layout.project_root is None
        or plan.instructions.project_root != plan.layout.project_root.resolve()
    ):
        raise ConfigError("DSH shared instruction plan belongs to another project")
    bodies: dict[str, str] = {}
    for result in plan.shared_rules:
        assert result.payload is not None
        rule = result.payload
        if rule.name in bodies and bodies[rule.name] != rule.body:
            raise ElementError(f"Conflicting DSH shared rule: {rule.name}")
        bodies[rule.name] = rule.body
        if plan.instructions is not None:
            for block in plan.instructions.blocks:
                if (
                    block.path == plan.layout.root_agents_md.resolve()
                    and block.name == rule.name
                    and block.body != rule.body
                ):
                    raise ElementError(f"Conflicting shared target union: {rule.name}")


def _validate_tree(value: object) -> TreeInventory:
    if not isinstance(value, dict) or "." not in value:
        raise ConfigError("DSH ownership needs a root inventory entry")
    for key, entry in value.items():
        if (
            not isinstance(key, str)
            or (key != "." and not _safe_relative(Path(key)))
            or not isinstance(entry, dict)
        ):
            raise ConfigError("Invalid DSH inventory path/entry")
        kind = entry.get("kind")
        if kind == "link":
            valid = isinstance(entry.get("target"), str)
        elif kind in ("file", "directory"):
            valid = type(entry.get("mode")) is int
            if kind == "file":
                valid = valid and isinstance(entry.get("sha256"), str)
        else:
            valid = False
        if not valid:
            raise ConfigError("Invalid DSH inventory file metadata")
    return cast(TreeInventory, value)


def read_dsh_inventory(layout: DshLayout) -> DshInventory:
    """Read only the explicitly named registry; refuse foreign/malformed data."""
    path = layout.provenance_path
    _guard(path, _anchor(layout))
    if path.is_symlink():
        raise LinkError(f"Refusing symlinked DSH ownership registry: {path}")
    if not path.exists():
        return DshInventory()
    try:
        data = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read DSH ownership registry {path}: {exc}") from exc
    if (
        not isinstance(data, dict)
        or data.get("managed_by") != "ai-dotfiles"
        or data.get("target") != "dsh"
        or type(data.get("schema_version")) is not int
        or data.get("schema_version") != DSH_OWNERSHIP_SCHEMA_VERSION
        or type(data.get("generator")) is not int
    ):
        raise ConfigError(f"Foreign/unsupported DSH ownership registry: {path}")
    records = data.get("records")
    sources, blocks = data.get("source_records"), data.get("rule_blocks")
    if (
        not isinstance(records, dict)
        or not isinstance(sources, dict)
        or not isinstance(blocks, dict)
    ):
        raise ConfigError(f"Invalid DSH ownership registry structure: {path}")
    for key, record in records.items():
        if (
            not isinstance(key, str)
            or not _safe_relative(Path(key))
            or not isinstance(record, dict)
        ):
            raise ConfigError(f"Invalid DSH output record: {key!r}")
        if _output_key(layout, layout.dsh_dir / key) != key:
            raise ConfigError(f"Noncanonical DSH output record: {key!r}")
        if (
            record.get("mode") not in ("copy", "link", "generated")
            or not isinstance(record.get("generators"), dict)
            or not isinstance(record.get("provenance"), list)
        ):
            raise ConfigError(f"Invalid DSH ownership metadata: {key}")
        generators, provenance = record["generators"], record["provenance"]
        if (
            not generators
            or not all(
                isinstance(name, str) and type(version) is int and version >= 0
                for name, version in generators.items()
            )
            or not provenance
            or not all(
                isinstance(item, dict)
                and all(
                    isinstance(item.get(field), str) and item[field]
                    for field in ("source", "origin", "element")
                )
                and isinstance(item.get("source_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"])
                and type(item.get("generator")) is int
                for item in provenance
            )
        ):
            raise ConfigError(f"Invalid DSH generator/provenance metadata: {key}")
        _validate_tree(record.get("output_inventory"))
        if (
            not isinstance(record.get("source_inventory"), dict)
            or not isinstance(record.get("source_tree_sha256"), str)
            or not (
                record.get("source") is None or isinstance(record.get("source"), str)
            )
        ):
            raise ConfigError(f"Invalid DSH source metadata: {key}")
        if record["source_inventory"]:
            _validate_tree(record["source_inventory"])
        if record["source_tree_sha256"] != _sha(_json(record["source_inventory"])):
            raise ConfigError(f"Invalid DSH resource tree digest: {key}")
        if (record["mode"] == "generated") != (record["source"] is None):
            raise ConfigError(f"Invalid DSH source/mode ownership: {key}")
    if not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in sources.items()
    ) or not all(
        isinstance(key, str)
        and isinstance(value, list)
        and all(isinstance(name, str) for name in value)
        for key, value in blocks.items()
    ):
        raise ConfigError(f"Invalid DSH contribution metadata: {path}")
    historical = data.get("shared_rule_records", {})
    if not isinstance(historical, dict) or not all(
        isinstance(key, str) for key in historical
    ):
        raise ConfigError(f"Invalid DSH historical rule registry: {path}")
    for key, value in historical.items():
        _validate_shared_custody(key, value)
    return DshInventory(
        cast(dict[str, DshOwnershipRecord], records), sources, blocks, historical
    )


def _verify_owned(path: Path, record: DshOwnershipRecord | None) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if record is None:
        raise LinkError(f"Foreign DSH destination; refusing replacement: {path}")
    actual = _inventory(path, follow_links=False)
    expected = record["output_inventory"]
    if any(expected.get(key) != value for key, value in actual.items()):
        raise LinkError(f"Foreign/modified data inside DSH owned destination: {path}")


def verify_dsh_owned_output(
    layout: DshLayout, relative_path: str, *, inventory: DshInventory | None = None
) -> bool:
    """Verify one recorded entry before lifecycle deletion; never scan a root.

    False means no ownership record. Foreign/modified existing data raises
    LinkError and must be preserved. Missing recorded output is still owned.
    """
    path = layout.dsh_dir / relative_path
    key = _output_key(layout, path)
    records = (
        inventory if inventory is not None else read_dsh_inventory(layout)
    ).records
    record = records.get(key)
    if record is None:
        return False
    _verify_owned(path, record)
    return True


def verify_dsh_local_rule_custody(
    layout: DshLayout,
    name: str,
    source_relative: str,
    *,
    inventory: DshInventory | None = None,
) -> str:
    """Prove an old local shared block from both original ownership records.

    The current original may have changed or disappeared. Its *previous* bytes
    must agree with the local source hash and the install source record, and an
    existing marker must still contain that exact body. This is not permission
    to replace a separately protected Codex/catalog contribution.
    """
    root = layout.project_root
    if root is None:
        raise ConfigError("Local DSH rule custody is project-only")
    _guard_local_registries(layout)
    registry = load_dsh_local_registry(root)
    source = root / source_relative
    if (
        not _safe_relative(Path(source_relative))
        or str(source.relative_to(root)) != source_relative
        or not source_relative.startswith(".claude/rules/")
        or source.suffix != ".md"
    ):
        raise ConfigError(f"Invalid local DSH rule custody source: {source_relative}")
    agents_md.block_markers(name)
    local = registry.sources.get(source_relative)
    records = inventory if inventory is not None else read_dsh_inventory(layout)
    candidates = _historical_shared_rules(records) or records.source_records
    previous = [
        record
        for record in candidates.values()
        if isinstance(record.get("provenance"), dict)
        and cast(dict[str, object], record["provenance"]).get("source") == str(source)
        and cast(dict[str, object], record["provenance"]).get("origin") == "local"
    ]
    if (
        local is None
        or local.get("kind") != "rule"
        or local.get("element") != f"rule:{source.stem}"
        or name not in registry.rule_blocks.get("AGENTS.md", [])
        or name not in records.rule_blocks.get("AGENTS.md", [])
        or len(previous) != 1
    ):
        raise LinkError(f"Unproven local DSH rule custody: {name}")
    current = [
        record
        for record in records.source_records.values()
        if isinstance(record.get("provenance"), dict)
        and cast(dict[str, object], record["provenance"]).get("source") == str(source)
        and cast(dict[str, object], record["provenance"]).get("origin") == "local"
    ]
    if len(current) != 1:
        raise LinkError(f"Unproven current local DSH rule custody: {name}")
    present = current[0]
    present_provenance = cast(dict[str, object], present["provenance"])
    present_text = present.get("source_text")
    if (
        present_provenance.get("element") != local["element"]
        or present_provenance.get("source_sha256") != local["source_sha256"]
        or present.get("status") != local["status"]
        or not isinstance(present_text, str)
        or _sha(present_text.encode()) != local["source_sha256"]
        or (
            present.get("status") == "READY"
            and (
                present.get("activation") not in ("shared", "literal")
                or not isinstance(present.get("body"), str)
                or split_body(
                    present_text.replace("\r\n", "\n").replace("\r", "\n")
                    if present.get("activation") == "shared"
                    else present_text
                )
                != cast(str, present["body"]).strip()
            )
        )
    ):
        raise LinkError(f"Conflicting current local DSH rule custody: {name}")
    prior = previous[0]
    provenance = cast(dict[str, object], prior["provenance"])
    text, body = prior.get("source_text"), prior.get("body")
    if (
        prior.get("managed_by") != "ai-dotfiles"
        or prior.get("target") != "dsh"
        or prior.get("status") != "READY"
        or prior.get("activation") != "shared"
        or prior.get("name") != name
        or provenance.get("element") != local["element"]
        or (
            not records.shared_rule_records
            and provenance.get("source_sha256") != local["source_sha256"]
        )
        or not isinstance(text, str)
        or _sha(text.encode("utf-8")) != provenance.get("source_sha256")
        or not isinstance(body, str)
        or split_body(text.replace("\r\n", "\n").replace("\r", "\n")) != body
    ):
        raise LinkError(f"Conflicting local DSH rule custody: {name}")
    target = layout.root_agents_md
    _guard(target, root)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise LinkError(f"Refusing foreign DSH AGENTS.md type: {target}")
    actual = target.read_bytes().decode("utf-8") if target.exists() else ""
    start, end = agents_md.block_markers(name)
    if actual.count(start) != actual.count(end) or actual.count(start) > 1:
        raise LinkError(f"Malformed/duplicate shared DSH block: {name}")
    if start in actual:
        _verify_shared_block(actual, name)
        if not agents_md.block_matches(name, body, actual):
            raise LinkError(f"Conflicting local DSH rule body: {name}")
    return body


def preflight_dsh_install(
    plan: DshInstallPlan, *, local_rule_custody: Mapping[str, str] | None = None
) -> DshInventory:
    """Check all outputs, registry and shared blocks before any materialization.

    Later lifecycle owners can reuse the same exact record/tree verification;
    retirement/prune and the desired/protected deletion union belong to them.
    This read-only operation never creates roots, profiles or snapshots.
    """
    for path, mode, digest in plan.permission_modes:
        if (
            manifest.get_dsh_permission_mode(path) != mode
            or _sha(path.read_bytes()) != digest
        ):
            raise ConfigError(
                f"DSH permission mode changed after planning: {path}; "
                "recollect the original sources before activation"
            )
    _validate_output_plan(plan)
    _guard_local_registries(plan.layout)
    inventory = read_dsh_inventory(plan.layout)
    # Omission is not isolation: native discovery still scans an existing
    # rejected bundle. Never let an unowned counterpart bypass admission.
    rejected_paths = (
        {
            plan.layout.skills_dir / result.provenance.source.parent.name
            for result in plan.skills
            if result.status != "READY"
        }
        | {
            plan.layout.skills_dir / path.parent.name
            for path, _ in plan.source_errors
            if path.name == "SKILL.md"
        }
        | set(plan.rejected_skill_paths)
    )
    for path in rejected_paths:
        _guard(path, _anchor(plan.layout))
        _verify_owned(path, inventory.records.get(_output_key(plan.layout, path)))
    # Retained history must still describe the actual block before any output
    # refresh, including a repeat migrate that now classifies the source MANUAL.
    historical = _historical_shared_rules(inventory)
    for record in historical.values():
        name = cast(str, record["name"])
        target = plan.layout.root_agents_md
        _guard(target, _anchor(plan.layout))
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise LinkError(f"Refusing foreign DSH AGENTS.md type: {target}")
        text = target.read_bytes().decode() if target.exists() else ""
        start, end = agents_md.block_markers(name)
        if text.count(start) != text.count(end) or text.count(start) > 1:
            raise LinkError(f"Malformed/duplicate shared DSH block: {name}")
        if start in text:
            _verify_shared_block(text, name)
            if not agents_md.block_matches(name, cast(str, record["body"]), text):
                raise LinkError(f"Conflicting historical DSH rule body: {name}")
    custody = local_rule_custody or {}
    for name, source in custody.items():
        if plan.layout.project_root is None:
            raise LinkError("Local DSH rule custody requires a project layout")
        verify_dsh_local_rule_custody(plan.layout, name, source, inventory=inventory)
        if not any(
            result.provenance.origin == "local"
            and result.provenance.source == plan.layout.project_root / source
            and result.payload is not None
            and result.payload.name == name
            for result in plan.shared_rules
        ):
            raise LinkError(f"Local DSH refresh has no matching desired rule: {name}")
    for result in (*plan.skills, *plan.agents, *plan.rules):
        _source_record(result)
    for output in plan.outputs:
        key = _output_key(plan.layout, output.path)
        _verify_owned(output.path, inventory.records.get(key))
        if (
            output.source is not None
            and _inventory(output.source, follow_links=True) != output.source_inventory
        ):
            raise LinkError(f"DSH source changed after planning: {output.source}")
    if plan.shared_rules:
        target = plan.layout.root_agents_md
        _guard(target, _anchor(plan.layout))
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise LinkError(f"Refusing foreign DSH AGENTS.md type: {target}")
        try:
            text = target.read_bytes().decode("utf-8") if target.exists() else ""
        except (OSError, UnicodeError) as exc:
            raise LinkError(
                f"Cannot read DSH shared instructions {target}: {exc}"
            ) from exc
        current_protection = (
            project_instruction_plan(
                (), (), plan.layout.project_root, Path(".")
            ).protected_blocks
            if plan.layout.project_root is not None
            else {}
        )
        for result in plan.shared_rules:
            assert result.payload is not None
            rule = result.payload
            start, end = agents_md.block_markers(rule.name)
            if text.count(start) != text.count(end) or text.count(start) > 1:
                raise LinkError(f"Malformed/duplicate shared DSH block: {rule.name}")
            if start in text and rule.name not in agents_md.iter_rule_block_names(text):
                raise LinkError(f"Malformed shared DSH block: {rule.name}")
            if start in text:
                _verify_shared_block(text, rule.name)
            if plan.instructions is not None:
                protected = plan.instructions.protected_blocks.get(
                    target.resolve(), set()
                ) | current_protection.get(target.resolve(), set())
                if rule.name in protected and not agents_md.block_matches(
                    rule.name, rule.body, text
                ):
                    codex_names = (
                        load_local_registry(plan.layout.project_root)[
                            "rule_blocks"
                        ].get("AGENTS.md", [])
                        if plan.layout.project_root is not None
                        else []
                    )
                    if rule.name not in custody or rule.name in codex_names:
                        raise LinkError(
                            f"Conflicting locally protected DSH block: {rule.name}"
                        )
    return inventory


def output_drift(
    output: DshOutput, record: DshOwnershipRecord | None
) -> tuple[str, ...]:
    """Read-only drift reasons; source content and link text are independent."""
    if record is None:
        return ("unrecorded",)
    reasons: list[str] = []
    if not output.path.exists() and not output.path.is_symlink():
        reasons.append("missing")
    elif _inventory(output.path, follow_links=False) != record["output_inventory"]:
        reasons.append("output changed")
    if record["generators"] != output.generators:
        reasons.append("generator changed")
    if [
        {key: value for key, value in item.items() if key != "generator"}
        for item in record["provenance"]
    ] != [
        {key: value for key, value in item.as_dict().items() if key != "generator"}
        for item in output.provenance
    ] or record[
        "source_inventory"
    ] != output.source_inventory:
        reasons.append("source changed")
    if record["mode"] != output.mode or record["source"] != (
        str(output.source.resolve()) if output.source else None
    ):
        reasons.append("mode/link changed")
    if (
        output.content is not None
        and output.path.is_file()
        and not output.path.is_symlink()
        and output.path.read_bytes() != output.content
    ):
        reasons.append("generated content changed")
    return tuple(reasons)


def _record(output: DshOutput) -> DshOwnershipRecord:
    return {
        "mode": output.mode,
        "source": str(output.source.resolve()) if output.source else None,
        "source_tree_sha256": _sha(_json(output.source_inventory)),
        "source_inventory": output.source_inventory,
        "output_inventory": _inventory(output.path, follow_links=False),
        "provenance": [item.as_dict() for item in output.provenance],
        "generators": output.generators,
    }


def skipped_skill_output_keys(
    plan: DshInstallPlan, inventory: DshInventory
) -> tuple[str, ...]:
    """Find only prior owned skill bundles for currently rejected originals.

    Ordinary removed sources remain the lifecycle owner's responsibility.
    Verification before deletion still rejects any foreign/modified contents.
    """
    rejected = (
        {
            str(result.provenance.source)
            for result in plan.skills
            if result.status != "READY"
        }
        | {str(path) for path in plan.rejected_skill_sources}
        | {str(path) for path, _ in plan.source_errors}
    )
    return tuple(
        key
        for key, record in inventory.records.items()
        if key.startswith("skills/")
        and key not in plan.desired_output_keys
        and any(part["source"] in rejected for part in record["provenance"])
    )


def apply_dsh_install(
    plan: DshInstallPlan,
    *,
    local_rule_custody: Mapping[str, str] | None = None,
    strict: bool = False,
) -> DshInstallResult:
    """Materialize a wholly preflighted plan, preserving unchanged bytes/mtimes.

    Existing primitives are destructive; DSH calls them only after proving exact
    ownership for every planned output. No adopt/backup-and-clobber is used.
    Old records are retained for later explicit retirement; this is not prune.
    """
    plan.require_activatable(strict=strict)
    previous = preflight_dsh_install(plan, local_rule_custody=local_rule_custody)
    retired_skills = skipped_skill_output_keys(plan, previous)
    for key in retired_skills:
        verify_dsh_owned_output(plan.layout, key, inventory=previous)
    records, sources = dict(previous.records), dict(previous.source_records)
    blocks = {key: list(names) for key, names in previous.rule_blocks.items()}
    historical = deepcopy(previous.shared_rule_records)
    # Capture prior authoritative READY bytes before current source_records can
    # replace them. Existing history was already validated against actual blocks.
    for key, prior in previous.source_records.items():
        if (
            prior.get("status") == "READY"
            and prior.get("activation") == "shared"
            and key not in historical
        ):
            _guard(plan.layout.root_agents_md, _anchor(plan.layout))
            if plan.layout.root_agents_md.is_symlink():
                raise LinkError("Refusing symlinked historical DSH instructions")
            candidate = {
                "schema_version": 1,
                "generator": DSH_SHARED_CUSTODY_GENERATOR_VERSION,
                "source_record": deepcopy(prior),
            }
            _validate_shared_custody(key, candidate)
            name = cast(str, prior["name"])
            text = (
                plan.layout.root_agents_md.read_bytes().decode()
                if plan.layout.root_agents_md.exists()
                else ""
            )
            start, end = agents_md.block_markers(name)
            if text.count(start) != text.count(end) or text.count(start) > 1:
                raise LinkError(f"Malformed/duplicate shared DSH block: {name}")
            if start in text:
                _verify_shared_block(text, name)
                if not agents_md.block_matches(name, cast(str, prior["body"]), text):
                    raise LinkError(f"Conflicting historical DSH rule body: {name}")
            historical[key] = candidate
    changed: list[Path] = []
    try:
        for key in retired_skills:
            path = plan.layout.dsh_dir / key
            if path.exists() or path.is_symlink():
                _clear_owned_output(path)
                changed.append(path)
            records.pop(key)
        for output in plan.outputs:
            key = _output_key(plan.layout, output.path)
            if output.mode == "generated":
                assert output.content is not None
                if output.path.is_symlink() or output.path.is_dir():
                    _clear_owned_output(output.path)
                if (
                    not output.path.is_file()
                    or output.path.read_bytes() != output.content
                ):
                    output.path.parent.mkdir(parents=True, exist_ok=True)
                    output.path.write_bytes(output.content)
                    changed.append(output.path)
            elif output.mode == "copy":
                assert output.source is not None
                if (
                    not output.path.exists()
                    or output.path.is_symlink()
                    or _inventory(output.path, follow_links=False)
                    != output.source_inventory
                ):
                    copy_tree_into(output.source, output.path)
                    changed.append(output.path)
            else:
                assert output.source is not None
                if output.path.exists() and not output.path.is_symlink():
                    _clear_owned_output(output.path)
                status = safe_symlink(
                    output.source,
                    output.path,
                    plan.layout.owned_dir / "unused-backup",
                    chmod_scripts=False,
                )
                if status != "already-linked":
                    changed.append(output.path)
            records[key] = _record(output)
        for result in (*plan.skills, *plan.agents, *plan.rules):
            sources[_source_id(result.provenance)] = _source_record(result)
        for result in plan.shared_rules:
            assert result.payload is not None
            rule = result.payload
            target = plan.layout.root_agents_md
            if (
                agents_md.upsert_rule_block(target, rule.name, rule.body)
                and target not in changed
            ):
                changed.append(target)
            block_key = str(target.relative_to(_anchor(plan.layout)))
            if rule.name not in blocks.setdefault(block_key, []):
                blocks[block_key].append(rule.name)
            historical[_source_id(result.provenance)] = {
                "schema_version": 1,
                "generator": DSH_SHARED_CUSTODY_GENERATOR_VERSION,
                "source_record": deepcopy(sources[_source_id(result.provenance)]),
            }
        inventory = DshInventory(records, sources, blocks, historical)
        data = _json(
            {
                "managed_by": "ai-dotfiles",
                "target": "dsh",
                "schema_version": DSH_OWNERSHIP_SCHEMA_VERSION,
                "generator": DSH_INSTALL_GENERATOR_VERSION,
                "records": records,
                "source_records": sources,
                "rule_blocks": blocks,
                "shared_rule_records": historical,
            }
        )
        registry = plan.layout.provenance_path
        if not registry.is_file() or registry.read_bytes() != data:
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_bytes(data)
            changed.append(registry)
    except (OSError, UnicodeError) as exc:
        raise LinkError(f"Cannot materialize DSH install: {exc}") from exc
    return DshInstallResult(tuple(changed), inventory, plan)
