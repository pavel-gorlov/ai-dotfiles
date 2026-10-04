"""Read fresh project-local Claude sources and plan faithful DSH migration.

One layout has one catalog/local install plan. The local registry retains only
provenance for lifecycle consumers; its stored values are never activation input.
Owned merged JSON exposes a guarded projection instead of reusing catalog data.
The current path-only native collectors cannot consume that projection, so it is
explicitly held pending their guarded-value integration, without disk snapshots.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

from ai_dotfiles.core import mcp_ownership, paths, settings_ownership
from ai_dotfiles.core.dsh_config import (
    DshConfigPlan,
    DshConfigSource,
    attach_dsh_config_outputs,
    collect_dsh_configuration,
    compose_dsh_configuration,
)
from ai_dotfiles.core.dsh_hooks import (
    DshHookPlan,
    DshHookSource,
    attach_dsh_hook_outputs,
    collect_dsh_hooks,
)
from ai_dotfiles.core.dsh_install import (
    DshInstallPlan,
    DshOutput,
    InstallMode,
    RenderResult,
    apply_dsh_install,
    plan_dsh_install,
    preflight_dsh_install,
    read_dsh_inventory,
)
from ai_dotfiles.core.dsh_layout import DshLayout, project_layout
from ai_dotfiles.core.dsh_local_registry import (
    DSH_LOCAL_GENERATOR_VERSION,
    DshLocalRegistry,
    guard_local_path,
    load_dsh_local_registry,
    save_dsh_local_registry,
    validate_dsh_local_registry,
)
from ai_dotfiles.core.dsh_permissions import merge_permission_policies
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
from ai_dotfiles.core.dsh_targets import project_target_plan
from ai_dotfiles.core.elements import ElementType
from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.local_discovery import (
    is_catalog_managed_path,
    iter_local_elements,
)
from ai_dotfiles.core.settings_merge import strip_owned

Classification = Literal["MECHANICAL", "REFACTOR", "MANUAL"]
LocalSourceKind = Literal["settings", "mcp", "hooks"]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()


@dataclass(frozen=True)
class DshSourceGuard:
    """Original file or absent ownership ledger observed during discovery."""

    path: Path
    source_sha256: str | None


@dataclass(frozen=True)
class DshLocalSource:
    """Fresh original and supported projection, never a stored aggregate.

    value strips only ledger-proven catalog permissions/hooks or MCP servers.
    unproven_fields names retained aggregate fields whose user origin cannot be
    reconstructed. Consumers must exclude these fields and keep their diagnostic
    restriction; equality with a current catalog fragment is not origin proof.
    requires_value_input distinguishes an owned projection from an unowned raw
    original that existing public path-only collectors can consume directly.
    """

    path: Path
    kind: LocalSourceKind
    provenance: DshProvenance
    original_value: dict[str, object]
    value: dict[str, object]
    guards: tuple[DshSourceGuard, ...]
    requires_value_input: bool
    unproven_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class DshMigrationAction:
    source: Path
    kind: str
    element: str
    strategy: str
    classification: Classification
    status: str
    diagnostics: tuple[DshDiagnostic, ...] = ()


@dataclass(frozen=True)
class DshLocalInputs:
    """Typed fresh producer boundary for migration, reconcile and launch.

    install is already the ONE catalog/local plan for layout. raw_sources retain
    guarded originals/projections; config_sources/hook_sources contain only raw
    inputs the existing path-only collectors can faithfully consume. Commands
    have their own flat native outputs and never sweep the command directory.
    """

    layout: DshLayout
    install: DshInstallPlan
    raw_sources: tuple[DshLocalSource, ...]
    config_sources: tuple[DshConfigSource, ...]
    hook_sources: tuple[DshHookSource, ...]
    commands: tuple[DshRenderResult[DshSkillPayload], ...]
    local_results: tuple[RenderResult, ...]
    actions: tuple[DshMigrationAction, ...]
    guards: tuple[DshSourceGuard, ...]

    @property
    def current_source_keys(self) -> frozenset[str]:
        assert self.layout.project_root is not None
        return frozenset(
            str(action.source.relative_to(self.layout.project_root))
            for action in self.actions
        )

    @property
    def diagnostics(self) -> tuple[DshDiagnostic, ...]:
        return tuple(item for action in self.actions for item in action.diagnostics)


@dataclass(frozen=True)
class DshMigrationPlan:
    inputs: DshLocalInputs
    install: DshInstallPlan
    config: DshConfigPlan
    hooks: DshHookPlan
    registry: DshLocalRegistry

    @property
    def diagnostics(self) -> tuple[DshDiagnostic, ...]:
        return (
            *self.inputs.diagnostics,
            *self.config.diagnostics,
            *self.config.permissions.diagnostics,
            *self.hooks.diagnostics,
        )

    @property
    def blocked(self) -> bool:
        # A MANUAL agent/rule stays recorded and produces no native contribution.
        # Unsupported config/hooks must not silently release a partial guard.
        return (
            any(source.requires_value_input for source in self.inputs.raw_sources)
            or self.config.blocked
            or self.hooks.blocked
        )

    @property
    def retired_source_keys(self) -> frozenset[str]:
        """Previously recorded originals absent from current discovery."""
        return frozenset(self.registry.sources) - self.inputs.current_source_keys

    @property
    def retired_output_keys(self) -> frozenset[str]:
        """Local output custody absent from the merged fresh desired plan."""
        return (
            frozenset(
                key
                for source in self.registry.sources.values()
                for key in cast(list[str], source["outputs"])
            )
            - self.install.desired_output_keys
        )


@dataclass(frozen=True)
class DshMigrateReport:
    actions: tuple[DshMigrationAction, ...]
    diagnostics: tuple[DshDiagnostic, ...]
    plan: DshMigrationPlan
    changed_paths: tuple[Path, ...] = ()
    dry_run: bool = False


def _guard_file(project_root: Path, path: Path) -> DshSourceGuard:
    guard_local_path(project_root, path)
    try:
        return DshSourceGuard(path, _sha(path.read_bytes()) if path.exists() else None)
    except OSError as exc:
        raise LinkError(f"Cannot read local DSH original/ownership: {path}") from exc


def verify_dsh_local_inputs(inputs: DshLocalInputs) -> None:
    """Prove original/ledger bytes and local bundle containment before writes."""
    assert inputs.layout.project_root is not None
    root = inputs.layout.project_root
    for guard in inputs.guards:
        current = _guard_file(root, guard.path)
        if current != guard:
            raise LinkError(f"Local DSH original/ownership changed: {guard.path}")
    fresh = {source.path: source for source in _local_json_sources(root)}
    if set(fresh) != {source.path for source in inputs.raw_sources}:
        raise LinkError("Local DSH original JSON source set changed after planning")
    for source in inputs.raw_sources:
        if fresh.get(source.path) != source:
            raise LinkError(
                f"Local DSH projection changed after planning: {source.path}"
            )
    for result in inputs.local_results:
        path = result.provenance.source
        guard_local_path(root, path)
        if isinstance(result.payload, DshSkillPayload):
            guard_local_path(root, result.payload.directory, tree=True)


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
        _json(value)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ConfigError(f"Cannot read local DSH original {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Local DSH source must be a JSON object: {path}")
    return cast(dict[str, object], value)


def _local_json_sources(root: Path) -> tuple[DshLocalSource, ...]:
    claude = paths.project_claude_dir(root)
    result = []
    for path, kind in (
        (claude / "settings.json", "settings"),
        (claude / "settings.local.json", "settings"),
        (root / ".mcp.json", "mcp"),
        (claude / "hooks.json", "hooks"),
    ):
        if not path.exists() and not path.is_symlink():
            continue
        guard = _guard_file(root, path)
        original = _read_json(path)
        value = deepcopy(original)
        ledger: Path | None = None
        unproven: tuple[str, ...] = ()
        if path == claude / "settings.json":
            ledger = settings_ownership.ownership_path(claude)
            guard_local_path(root, ledger)
            if ledger.exists():
                value = strip_owned(
                    value, settings_ownership.load_settings_ownership(claude)
                )
                unproven = tuple(sorted(original.keys() - {"permissions", "hooks"}))
        elif kind == "mcp":
            ledger = mcp_ownership.ownership_path(claude)
            guard_local_path(root, ledger)
            if ledger.exists():
                owned = mcp_ownership.load_ownership(claude)
                servers = value.get("mcpServers")
                if isinstance(servers, dict):
                    value["mcpServers"] = {
                        name: server
                        for name, server in servers.items()
                        if name not in owned
                    }
        guards = (guard,) + ((_guard_file(root, ledger),) if ledger else ())
        relative = str(path.relative_to(root))
        result.append(
            DshLocalSource(
                path,
                cast(LocalSourceKind, kind),
                DshProvenance(
                    path,
                    "local",
                    relative,
                    cast(str, guard.source_sha256),
                    DSH_LOCAL_GENERATOR_VERSION,
                ),
                original,
                value,
                guards,
                ledger is not None and ledger.exists(),
                unproven,
            )
        )
    return tuple(result)


def _classification(result: RenderResult) -> Classification:
    if result.status == "MANUAL":
        return "MANUAL"
    if result.status == "DEFERRED" or result.diagnostics:
        return "REFACTOR"
    return "MECHANICAL"


def _command_result(
    source: Path, metadata: Mapping[str, object] | None
) -> DshRenderResult[DshSkillPayload]:
    result = validate_skill(
        source,
        origin="local",
        element=f"command:{source.stem}",
        native_frontmatter=metadata,
    )
    if result.status != "READY":
        return result
    assert result.payload is not None and result.payload.invocation is not None
    diagnostics = list(result.diagnostics)
    if result.payload.invocation["modelInvocable"]:
        diagnostics.append(
            DshDiagnostic(
                "COMMAND_ACTIVATION_UNPROVEN",
                "local",
                result.provenance.element,
                "disable-model-invocation",
                "Command requires explicit on-demand semantics "
                "(disable-model-invocation: true); model activation cannot be inferred",
            )
        )
    # Claude command substitutions are executable/import semantics, not prose.
    if "!`" in result.payload.body or re.search(
        r"\$(?:ARGUMENTS|[0-9]+)|\$\{CLAUDE_PLUGIN_ROOT\}|(?:^|\s)@\S+",
        result.payload.body,
    ):
        diagnostics.append(
            DshDiagnostic(
                "COMMAND_EXECUTION_UNMAPPED",
                "local",
                result.provenance.element,
                "body",
                "Command shell substitution, arguments or imports "
                "require manual adaptation",
            )
        )
    if any(item.blocking for item in diagnostics):
        return replace(
            result, payload=None, diagnostics=tuple(diagnostics), status="MANUAL"
        )
    return result


def merge_dsh_local_install(
    catalog: DshInstallPlan, local: DshInstallPlan
) -> DshInstallPlan:
    """Merge one layout before composition; refuse same-scope name collisions."""
    if catalog.layout != local.layout or local.layout.project_root is None:
        raise ConfigError(
            "Local DSH migration is project-only and requires one matching layout"
        )
    for field_name in ("skills", "agents", "rules"):
        seen: set[str] = set()
        for result in (*getattr(catalog, field_name), *getattr(local, field_name)):
            if result.status == "READY" and result.payload is not None:
                name = result.payload.name
                if name in seen:
                    raise ConfigError(
                        f"Catalog/local DSH {field_name} name collision: {name}"
                    )
                seen.add(name)
    plan = plan_dsh_install(
        local.layout,
        skills=(*catalog.skills, *local.skills),
        agents=(*catalog.agents, *local.agents),
        rules=(*catalog.rules, *local.rules),
        resources=(*catalog.resources, *local.resources),
        permissions=merge_permission_policies((catalog.permissions, local.permissions)),
        instructions=catalog.instructions,
    )
    # Retain source link/copy modes and externally attached producer outputs.
    retained: dict[Path, DshOutput] = {}
    for output in (*catalog.outputs, *local.outputs):
        prior = retained.get(output.path)
        if prior is not None and prior != output:
            raise ConfigError(f"Conflicting catalog/local DSH output: {output.path}")
        retained[output.path] = output
    return replace(plan, outputs=tuple(retained.values()))


def collect_dsh_local_inputs(
    project_root: Path,
    *,
    manifest_packages: Iterable[str] | None = None,
    catalog_plan: DshInstallPlan | None = None,
    mode: InstallMode = "link",
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
) -> DshLocalInputs:
    """Discover fresh originals without snapshots, profiles or runtime writes.

    DEFERRED metadata is retried by calling this function with results from the
    public native_frontmatter parser. Its original-path keys are unchanged.
    """
    root = project_root.absolute()
    layout = project_layout(root)
    if catalog_plan is not None and catalog_plan.layout != layout:
        raise ConfigError("Local DSH migration is project-only; catalog layout differs")
    load_dsh_local_registry(root)
    if catalog_plan is None and any(
        part["origin"] not in ("local", "builtin")
        for record in read_dsh_inventory(layout).records.values()
        for part in record["provenance"]
    ):
        raise ConfigError(
            "Existing catalog DSH contributions require a fresh merged catalog plan"
        )
    claude = paths.project_claude_dir(root)
    guard_local_path(root, claude)
    metadata = native_frontmatter or {}
    skills: list[DshRenderResult[DshSkillPayload]] = []
    agents: list[DshRenderResult[DshAgentPayload]] = []
    rules: list[DshRenderResult[DshRulePayload]] = []
    actions: list[DshMigrationAction] = []
    guards = [_guard_file(root, claude / ".ai-dotfiles-copies.json")]
    results: list[RenderResult] = []
    for element in iter_local_elements(root, manifest_packages=manifest_packages):
        path = element.source_path
        guard_local_path(root, path, tree=element.type is ElementType.SKILL)
        if element.type is ElementType.SKILL:
            path /= "SKILL.md"
            rendered: RenderResult = validate_skill(
                path,
                origin="local",
                element=element.raw,
                native_frontmatter=metadata.get(path),
            )
            skills.append(cast(DshRenderResult[DshSkillPayload], rendered))
        elif element.type is ElementType.AGENT:
            rendered = render_agent(
                path,
                origin="local",
                element=element.raw,
                native_frontmatter=metadata.get(path),
            )
            agents.append(rendered)
        else:
            rendered = render_rule(
                path,
                origin="local",
                element=element.raw,
                native_frontmatter=metadata.get(path),
            )
            rules.append(rendered)
        guards.append(_guard_file(root, path))
        results.append(rendered)
        actions.append(
            DshMigrationAction(
                path,
                element.type.value,
                element.raw,
                "native-" + element.type.value,
                _classification(rendered),
                rendered.status,
                rendered.diagnostics,
            )
        )
    commands = []
    command_outputs = []
    directory = claude / "commands"
    if directory.is_dir():
        guard_local_path(root, directory)
        for command_source in sorted(directory.rglob("*.md")):
            if any(
                part.startswith(".")
                for part in command_source.relative_to(directory).parts
            ) or is_catalog_managed_path(command_source, root):
                continue
            guard_local_path(root, command_source)
            command = _command_result(command_source, metadata.get(command_source))
            commands.append(command)
            guards.append(_guard_file(root, command_source))
            actions.append(
                DshMigrationAction(
                    command_source,
                    "command",
                    command.provenance.element,
                    "native-on-demand-skill",
                    _classification(command),
                    command.status,
                    command.diagnostics,
                )
            )
            if command.status == "READY":
                assert command.payload is not None
                command_outputs.append(
                    DshOutput(
                        layout.skills_dir / f"{command.payload.name}.md",
                        "generated",
                        (command.provenance,),
                        {
                            "local": DSH_LOCAL_GENERATOR_VERSION,
                            "render": command.provenance.generator,
                        },
                        content=command_source.read_bytes(),
                    )
                )
    raw_sources = _local_json_sources(root)
    config_sources = []
    hook_sources = []
    for source in raw_sources:
        guards.extend(source.guards)
        diagnostics = []
        if source.requires_value_input:
            diagnostics.append(
                DshDiagnostic(
                    "LOCAL_VALUE_INPUT_PENDING",
                    "local",
                    source.provenance.element,
                    source.kind,
                    "Owned merged input requires a guarded in-memory projection; "
                    "current path-only collectors cannot activate its local view",
                )
            )
        for field_name in source.unproven_fields:
            diagnostics.append(
                DshDiagnostic(
                    "LOCAL_ORIGINAL_UNPROVEN",
                    "local",
                    source.provenance.element,
                    field_name,
                    "Claude ownership ledger tracks permission strings and hook "
                    "signatures only; this aggregate field has no provable "
                    "original local-user origin",
                )
            )
        actions.append(
            DshMigrationAction(
                source.path,
                source.kind,
                source.provenance.element,
                "native-configuration",
                (
                    "MANUAL"
                    if source.unproven_fields
                    else "REFACTOR" if diagnostics else "MECHANICAL"
                ),
                "HELD" if diagnostics else "READY",
                tuple(diagnostics),
            )
        )
        if source.requires_value_input:
            continue
        if source.kind == "hooks":
            hook_sources.append(
                DshHookSource(
                    source.path, "project", "local", source.provenance.element
                )
            )
        else:
            config_sources.append(
                DshConfigSource(
                    source.path,
                    source.kind,
                    "project",
                    "local",
                    source.provenance.element,
                    root,
                )
            )
    local = plan_dsh_install(
        layout, skills=skills, agents=agents, rules=rules, mode=mode
    )
    local = replace(local, outputs=(*local.outputs, *command_outputs))
    install = (
        merge_dsh_local_install(catalog_plan, local)
        if catalog_plan is not None
        else local
    )
    names = [
        result.payload.name
        for result in (*install.skills, *commands)
        if result.status == "READY" and result.payload is not None
    ]
    if len(names) != len(set(names)):
        raise ConfigError("Catalog/local DSH skill/command name collision")
    inputs = DshLocalInputs(
        layout,
        install,
        raw_sources,
        tuple(config_sources),
        tuple(hook_sources),
        tuple(commands),
        tuple(results),
        tuple(actions),
        tuple(dict.fromkeys(guards)),
    )
    verify_dsh_local_inputs(inputs)
    return inputs


def _registry_for(
    inputs: DshLocalInputs,
    install: DshInstallPlan,
    config: DshConfigPlan,
    hooks: DshHookPlan,
) -> DshLocalRegistry:
    assert inputs.layout.project_root is not None
    root = inputs.layout.project_root
    previous = load_dsh_local_registry(root)
    sources = deepcopy(previous.sources)
    blocks = deepcopy(previous.rule_blocks)
    original_by_path = {source.path: source for source in inputs.raw_sources}
    for action in inputs.actions:
        source = action.source
        original = original_by_path.get(source)
        part_outputs = [
            output
            for output in install.outputs
            if any(part.source == source for part in output.provenance)
        ]
        contributions = [
            part.name
            for part in config.contributions
            if any(provenance.source == source for provenance in part.provenance)
        ]
        if any(part.source == source for part in hooks.provenance) and hooks.hooks:
            contributions.append("hooks")
        key = str(source.relative_to(root))
        prior = sources.get(key, {})
        desired_outputs = sorted(
            str(output.path.relative_to(inputs.layout.dsh_dir))
            for output in part_outputs
        )
        record: dict[str, object] = {
            "source": key,
            "source_sha256": _sha(source.read_bytes()),
            "generator": DSH_LOCAL_GENERATOR_VERSION,
            "kind": action.kind,
            "element": action.element,
            "classification": action.classification,
            "status": action.status,
            "diagnostics": [asdict(item) for item in action.diagnostics],
            "outputs": sorted(
                set(cast(list[str], prior.get("outputs", []))) | set(desired_outputs)
            ),
            "desired_outputs": desired_outputs,
            "resources": sorted(
                set(cast(list[str], prior.get("resources", [])))
                | {
                    str(output.path.relative_to(inputs.layout.dsh_dir))
                    for output in part_outputs
                    if output.source is not None
                }
            ),
            "contributions": sorted(
                set(cast(list[str], prior.get("contributions", [])))
                | set(contributions)
            ),
            "desired_contributions": sorted(set(contributions)),
            "guards": [
                {
                    "source": str(guard.path.relative_to(root)),
                    "source_sha256": guard.source_sha256,
                }
                for guard in (original.guards if original else inputs.guards)
                if guard.path == source
                or (original is not None and guard.path != source)
            ],
            "provenance": [
                part.as_dict()
                for output in part_outputs
                for part in output.provenance
                if part.source == source
            ],
            "output_generators": {
                **cast(dict[str, object], prior.get("output_generators", {})),
                **{
                    str(
                        output.path.relative_to(inputs.layout.dsh_dir)
                    ): output.generators
                    for output in part_outputs
                },
            },
        }
        if original is not None:
            record.update(
                value=deepcopy(original.value),
                unproven_fields=list(original.unproven_fields),
                requires_value_input=original.requires_value_input,
            )
        sources[key] = record
    for result in inputs.install.shared_rules:
        if result in inputs.local_results:
            assert result.payload is not None
            names = blocks.setdefault("AGENTS.md", [])
            if result.payload.name not in names:
                names.append(result.payload.name)
    registry = DshLocalRegistry(sources, blocks)
    validate_dsh_local_registry(root, registry)
    return registry


def plan_dsh_migration(
    inputs: DshLocalInputs,
    *,
    config_sources: Sequence[DshConfigSource] = (),
    hook_sources: Sequence[DshHookSource] = (),
) -> DshMigrationPlan:
    """Compose raw sources once, with exactly one combined hook contribution.

    External sources are original catalog/global inputs, not merged snapshots.
    Owned local projections remain in inputs with an explicit activation hold.
    """
    verify_dsh_local_inputs(inputs)
    sources = (*config_sources, *inputs.config_sources)
    hooks = collect_dsh_hooks(
        (*sources, *hook_sources, *inputs.hook_sources),
        inputs.layout,
        project_root=inputs.layout.project_root,
    )
    assert inputs.layout.project_root is not None
    for resource in hooks.resources:
        if resource.provenance.origin == "local":
            guard_local_path(inputs.layout.project_root, resource.source, tree=True)
    contribution = None if hooks.blocked else hooks.contribution()
    contributions = (contribution,) if contribution is not None else ()
    config = collect_dsh_configuration(
        sources, inputs.layout, contributions=contributions
    )
    install = inputs.install
    if (
        not config.blocked
        and not hooks.blocked
        and not any(source.requires_value_input for source in inputs.raw_sources)
    ):
        assert inputs.layout.project_root is not None
        config = compose_dsh_configuration(
            config,
            (install,),
            target_plans=(project_target_plan(inputs.layout.project_root),),
        )
        if hooks.sources:
            install = attach_dsh_hook_outputs(install, hooks)
        install = attach_dsh_config_outputs(install, config)
        # Config's path-only producer knows JSON contributions; add the rendered
        # original provenance used by its aggregate rows. Empty compositions use
        # the actual builtin bridge/audit provenance instead of an empty ledger.
        rendered_provenance = tuple(
            result.provenance
            for result in (*install.skills, *install.agents, *install.rules)
        ) + tuple(result.provenance for result in inputs.commands)
        builtin_provenance = next(
            output.provenance
            for output in install.outputs
            if output.path == inputs.layout.bridge_path
        )
        install = replace(
            install,
            outputs=tuple(
                (
                    replace(
                        output,
                        provenance=tuple(
                            dict.fromkeys((*output.provenance, *rendered_provenance))
                        )
                        or builtin_provenance,
                    )
                    if output.path
                    in (inputs.layout.config_path, inputs.layout.patch_path)
                    else output
                )
                for output in install.outputs
            ),
        )
    # Config/hook diagnostics classify each local original, including exact field.
    actions = []
    for action in inputs.actions:
        diagnostics = tuple(
            item
            for item in (
                *config.diagnostics,
                *config.permissions.diagnostics,
                *hooks.diagnostics,
            )
            if item.origin == "local" and item.element == action.element
        )
        if diagnostics:
            action = replace(
                action,
                classification=(
                    "MANUAL"
                    if any(item.blocking for item in diagnostics)
                    else "REFACTOR"
                ),
                status=(
                    "MANUAL"
                    if any(item.blocking for item in diagnostics)
                    else action.status
                ),
                diagnostics=(*action.diagnostics, *diagnostics),
            )
        actions.append(action)
    inputs = replace(inputs, actions=tuple(actions))
    registry = _registry_for(inputs, install, config, hooks)
    return DshMigrationPlan(inputs, install, config, hooks, registry)


def migrate_to_dsh(
    project_root: Path,
    *,
    manifest_packages: Iterable[str] | None = None,
    catalog_plan: DshInstallPlan | None = None,
    config_sources: Sequence[DshConfigSource] = (),
    hook_sources: Sequence[DshHookSource] = (),
    mode: InstallMode = "link",
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
    dry_run: bool = False,
) -> DshMigrateReport:
    """Project-only migration; dry-run writes zero bytes, including snapshots."""
    inputs = collect_dsh_local_inputs(
        project_root,
        manifest_packages=manifest_packages,
        catalog_plan=catalog_plan,
        mode=mode,
        native_frontmatter=native_frontmatter,
    )
    plan = plan_dsh_migration(
        inputs, config_sources=config_sources, hook_sources=hook_sources
    )
    changed: tuple[Path, ...] = ()
    preflight_dsh_install(plan.install)
    if not dry_run:
        if plan.blocked:
            raise ConfigError(
                "Cannot activate local DSH migration: "
                + "; ".join(
                    f"{item.origin} {item.element} {item.field}: {item.reason}"
                    for item in plan.diagnostics
                    if item.blocking
                )
            )
        verify_dsh_local_inputs(plan.inputs)
        validate_dsh_local_registry(project_root, plan.registry)
        preflight_dsh_install(plan.install)
        result = apply_dsh_install(plan.install)
        changed = result.changed_paths
        if save_dsh_local_registry(project_root, plan.registry):
            changed += (plan.inputs.layout.local_registry_path,)
    return DshMigrateReport(
        plan.inputs.actions, plan.diagnostics, plan, changed, dry_run
    )
