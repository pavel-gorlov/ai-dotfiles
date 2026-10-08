"""Fresh DSH reconciliation and retirement with bounded, verified ownership.

Only explicitly inventoried outputs and intact recorded Markdown blocks can be
retired. A check builds the same plan and changes no filesystem metadata. Native
profiles and stored aggregate configuration never supply activation input.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import cast

from ai_dotfiles.core import agents_md
from ai_dotfiles.core.codex_local_registry import load_local_registry, registry_path
from ai_dotfiles.core.codex_render import split_body
from ai_dotfiles.core.dsh_admission import require_admission, skipped_diagnostics
from ai_dotfiles.core.dsh_config import (
    DshConfigSource,
    attach_dsh_config_outputs,
    collect_dsh_config_sources,
    collect_dsh_configuration,
    compose_dsh_configuration,
)
from ai_dotfiles.core.dsh_hooks import (
    DshHookSource,
    attach_dsh_hook_outputs,
    collect_dsh_hooks,
)
from ai_dotfiles.core.dsh_install import (
    DSH_INSTALL_GENERATOR_VERSION,
    DSH_OWNERSHIP_SCHEMA_VERSION,
    DshInstallPlan,
    DshInventory,
    InstallMode,
    apply_dsh_install,
    collect_dsh_elements,
    output_drift,
    preflight_dsh_install,
    read_dsh_inventory,
    verify_dsh_local_rule_custody,
    verify_dsh_owned_output,
)
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import (
    DshLocalRegistry,
    guard_local_path,
    load_dsh_local_registry,
    save_dsh_local_registry,
    validate_dsh_local_registry,
)
from ai_dotfiles.core.dsh_migrate import (
    DshLocalInputs,
    DshMigrationPlan,
    collect_dsh_local_inputs,
    plan_dsh_migration,
    verify_dsh_local_inputs,
)
from ai_dotfiles.core.dsh_render import DshDiagnostic
from ai_dotfiles.core.dsh_targets import global_target_plan, project_target_plan
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.shared_instructions import project_instruction_plan
from ai_dotfiles.core.targets import Target


@dataclass(frozen=True)
class DshReconcilePlan:
    """One per-layout desired plan plus preflighted retirement and original guards."""

    install: DshInstallPlan
    previous: DshInventory
    drift: tuple[str, ...]
    retired_outputs: tuple[str, ...]
    retired_blocks: dict[Path, set[str]]
    removed_blocks: dict[Path, set[str]]
    local_rule_custody: dict[str, str]
    guards: tuple[tuple[Path, str | None], ...]
    migration: DshMigrationPlan | None = None
    local_registry: DshLocalRegistry | None = None
    protected_sources: tuple[tuple[Path, str], ...] = ()
    activation_diagnostics: tuple[DshDiagnostic, ...] = ()

    @property
    def diagnostics(self) -> tuple[DshDiagnostic, ...]:
        return (
            self.migration.diagnostics
            if self.migration
            else (*self.install.diagnostics, *self.activation_diagnostics)
        )

    @property
    def skipped(self) -> tuple[DshDiagnostic, ...]:
        return skipped_diagnostics(self.diagnostics)

    @property
    def partial(self) -> bool:
        return bool(self.skipped)


@dataclass
class DshReconcileReport:
    """Drift and actual writes; check failure can be consumed directly by the CLI."""

    drift: list[str] = field(default_factory=list)
    check_only: bool = False
    changed_paths: tuple[Path, ...] = ()
    diagnostics: tuple[DshDiagnostic, ...] = ()

    @property
    def skipped(self) -> tuple[DshDiagnostic, ...]:
        return skipped_diagnostics(self.diagnostics)

    @property
    def partial(self) -> bool:
        return bool(self.skipped)

    @property
    def exit_code(self) -> int:
        return int(self.check_only and bool(self.drift))


def _digest(path: Path) -> str | None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise LinkError(f"Refusing redirected DSH lifecycle input: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def _inventory_bytes(inventory: DshInventory) -> bytes:
    return _bytes(
        {
            "managed_by": "ai-dotfiles",
            "target": "dsh",
            "schema_version": DSH_OWNERSHIP_SCHEMA_VERSION,
            "generator": DSH_INSTALL_GENERATOR_VERSION,
            "records": inventory.records,
            "source_records": inventory.source_records,
            "rule_blocks": inventory.rule_blocks,
            "shared_rule_records": inventory.shared_rule_records,
        }
    )


def _guard_destination(layout: DshLayout, path: Path) -> None:
    anchor = layout.project_root or layout.dsh_dir
    absolute, root = path.absolute(), anchor.absolute()
    if ".." in absolute.parts or not absolute.is_relative_to(root):
        raise LinkError(f"DSH lifecycle destination is outside its root: {path}")
    for parent in reversed(absolute.parents):
        if parent.is_relative_to(root) and (
            parent.is_symlink() or (parent.exists() and not parent.is_dir())
        ):
            raise LinkError(f"Refusing redirected DSH lifecycle parent: {parent}")
    if layout.project_root is not None:
        guard_local_path(layout.project_root, path.parent, destination=True)


def _block_body(inventory: DshInventory, name: str) -> str:
    bodies: set[str] = set()
    candidates = (
        [
            cast(dict[str, object], value["source_record"])
            for value in inventory.shared_rule_records.values()
        ]
        if inventory.shared_rule_records
        else list(inventory.source_records.values())
    )
    for record in candidates:
        if record.get("name") != name or record.get("activation") != "shared":
            continue
        provenance, text, body = (
            record.get("provenance"),
            record.get("source_text"),
            record.get("body"),
        )
        if (
            record.get("managed_by") != "ai-dotfiles"
            or record.get("target") != "dsh"
            or record.get("status") != "READY"
            or not isinstance(provenance, dict)
            or not isinstance(text, str)
            or not isinstance(body, str)
            or hashlib.sha256(text.encode()).hexdigest()
            != provenance.get("source_sha256")
            or split_body(text.replace("\r\n", "\n").replace("\r", "\n")) != body
        ):
            raise LinkError(f"Unproven DSH shared block source: {name}")
        bodies.add(body)
    if len(bodies) != 1:
        raise LinkError(f"Unproven DSH shared block custody: {name}")
    return bodies.pop()


def _verify_block(path: Path, name: str, body: str) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise LinkError(f"Refusing foreign shared instructions: {path}")
    text = path.read_bytes().decode() if path.exists() else ""
    start, end = agents_md.block_markers(name)
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise LinkError(f"Malformed/duplicate shared DSH block: {name}")
    if start not in text:
        return
    # Compare the entire span, not merely a user-editable SHA header.
    body_text = body.strip()
    digest = hashlib.sha256(body_text.encode()).hexdigest()
    expected = (
        f"{start}\n<!-- ai-dotfiles:rule:{name} sha256:{digest} -->\n"
        f"{body_text}\n{end}"
    )
    actual = text[text.index(start) : text.index(end) + len(end)]
    if actual.replace("\r\n", "\n") != expected:
        raise LinkError(f"Foreign/modified shared DSH block: {name}")


def _local_custody(
    layout: DshLayout, inventory: DshInventory, registry: DshLocalRegistry
) -> dict[str, str]:
    custody: dict[str, str] = {}
    for name in registry.rule_blocks.get("AGENTS.md", []):
        matches = [
            key
            for key, record in registry.sources.items()
            if record["kind"] == "rule" and record["element"] == f"rule:{name}"
        ]
        if len(matches) != 1:
            raise LinkError(f"Unproven local DSH shared block custody: {name}")
        verify_dsh_local_rule_custody(layout, name, matches[0], inventory=inventory)
        custody[name] = matches[0]
    return custody


def _current_local_registry(migration: DshMigrationPlan) -> DshLocalRegistry:
    sources = {
        key: deepcopy(value)
        for key, value in migration.registry.sources.items()
        if key in migration.inputs.current_source_keys
    }
    for record in sources.values():
        desired = cast(list[str], record["desired_outputs"])
        record["outputs"] = list(desired)
        record["resources"] = [
            key for key in cast(list[str], record["resources"]) if key in desired
        ]
        record["output_generators"] = {
            key: value
            for key, value in cast(
                dict[str, object], record["output_generators"]
            ).items()
            if key in desired
        }
        record["contributions"] = list(cast(list[str], record["desired_contributions"]))
    names = sorted(
        {
            result.payload.name
            for result in migration.inputs.install.shared_rules
            if result in migration.inputs.local_results and result.payload is not None
        }
    )
    return DshLocalRegistry(sources, {"AGENTS.md": names} if names else {})


def _verify_local_catalog_plan(inputs: DshLocalInputs, catalog: DshInstallPlan) -> None:
    """Prove the supplied producer retained this fresh catalog before composition."""
    if (
        catalog.layout.project_root is None
        or inputs.layout != catalog.layout
        or inputs.install.layout != catalog.layout
    ):
        raise ConfigError(
            "Local DSH reconciliation requires one matching project layout"
        )
    verify_dsh_local_inputs(inputs)
    supplied_catalog = replace(
        inputs.install,
        skills=tuple(
            r for r in inputs.install.skills if r.provenance.origin != "local"
        ),
        agents=tuple(
            r for r in inputs.install.agents if r.provenance.origin != "local"
        ),
        rules=tuple(r for r in inputs.install.rules if r.provenance.origin != "local"),
        resources=tuple(
            r for r in inputs.install.resources if r.provenance.origin != "local"
        ),
        outputs=tuple(
            output
            for output in inputs.install.outputs
            if any(part.origin != "local" for part in output.provenance)
        ),
    )
    if supplied_catalog != catalog:
        raise ConfigError(
            "Supplied local DSH inputs disagree with the fresh catalog plan"
        )


def plan_dsh_reconciliation(
    layout: DshLayout,
    packages: Sequence[str],
    catalog: Path,
    *,
    targets: Sequence[Target] = (Target.DSH,),
    include_catalog: bool = True,
    mode: InstallMode = "link",
    config_sources: Sequence[DshConfigSource] = (),
    hook_sources: Sequence[DshHookSource] = (),
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
    local_inputs: DshLocalInputs | None = None,
    strict: bool = False,
) -> DshReconcilePlan:
    """Collect fresh catalog/local originals and prove every retirement first.

    A project local registry opts that scope into the existing migration
    producer. Global scope has no local migration. Disabled catalog targets
    still retain migrated locals and the independent Codex instruction union.
    Unsupported owned projections remain an explicit activation hold.
    A supplied fresh producer selects local originals; it is verified against
    this layout/catalog and composed once without repeating local discovery.
    """
    selected = parse_elements(list(packages)) if include_catalog else []
    install = collect_dsh_elements(
        selected,
        layout,
        catalog,
        mode=mode,
        targets=targets,
        native_frontmatter=native_frontmatter,
        strict=strict,
    )
    if local_inputs is not None:
        _verify_local_catalog_plan(local_inputs, install)
    previous = read_dsh_inventory(layout)
    sources = (
        *config_sources,
        *collect_dsh_config_sources(selected, catalog, layout),
    )
    migration = None
    registry = None
    custody: dict[str, str] = {}
    if layout.project_root is not None:
        old_local = load_dsh_local_registry(layout.project_root)
        custody = _local_custody(layout, previous, old_local)
        if local_inputs is not None or old_local.sources or old_local.rule_blocks:
            inputs = local_inputs or collect_dsh_local_inputs(
                layout.project_root,
                manifest_packages=packages,
                catalog_plan=install,
                mode=mode,
                native_frontmatter=native_frontmatter,
                strict=strict,
            )
            migration = plan_dsh_migration(
                inputs,
                config_sources=sources,
                hook_sources=hook_sources,
                strict=strict,
            )
            require_admission(
                migration.diagnostics,
                strict=strict,
                context="Cannot reconcile local DSH activation",
            )
            install = migration.install
            registry = _current_local_registry(migration)
            validate_dsh_local_registry(layout.project_root, registry)
    if migration is None:
        hooks = collect_dsh_hooks(
            (*sources, *hook_sources),
            layout,
            project_root=layout.project_root,
            install_plans=(install,),
        )
        contribution = hooks.contribution(strict=strict)
        config = collect_dsh_configuration(
            sources,
            layout,
            contributions=(contribution,) if contribution is not None else (),
            strict=strict,
        )
        config = compose_dsh_configuration(
            config,
            (install,),
            target_plans=(
                (
                    project_target_plan(layout.project_root)
                    if layout.project_root
                    else global_target_plan(layout.dsh_dir)
                ),
            ),
        )
        if hooks.sources:
            install = attach_dsh_hook_outputs(install, hooks, strict=strict)
        install = attach_dsh_config_outputs(install, config)
        # Aggregate rows depend on rendered originals as well as JSON sources.
        provenance = tuple(
            dict.fromkeys(
                part for output in install.outputs for part in output.provenance
            )
        )
        install = replace(
            install,
            outputs=tuple(
                (
                    replace(output, provenance=output.provenance or provenance)
                    if output.path in (layout.config_path, layout.patch_path)
                    else output
                )
                for output in install.outputs
            ),
        )
    active = bool(
        install.skills
        or install.agents
        or install.rules
        or install.resources
        or sources
        or (migration and migration.inputs.raw_sources)
        or hook_sources
    )
    if not active:
        install = replace(install, outputs=())
    union = None
    if layout.project_root is not None:
        union = project_instruction_plan(
            parse_elements(list(packages)),
            (
                targets
                if include_catalog
                else tuple(target for target in targets if target is not Target.DSH)
            ),
            layout.project_root,
            catalog,
        )
        install = replace(install, instructions=union)
    refresh_custody = {
        result.payload.name: custody[result.payload.name]
        for result in install.shared_rules
        if result.payload is not None
        and result.provenance.origin == "local"
        and result.payload.name in custody
    }
    preflight_dsh_install(install, local_rule_custody=refresh_custody)
    drift: list[str] = []
    for output in install.outputs:
        key = str(output.path.relative_to(layout.dsh_dir))
        reasons = output_drift(output, previous.records.get(key))
        if reasons:
            drift.append(f"{key} ({', '.join(reasons)})")
    retired = tuple(sorted(set(previous.records) - install.desired_output_keys))
    for key in retired:
        verify_dsh_owned_output(layout, key, inventory=previous)
        drift.append(f"{key} (retired)")
    keep: dict[Path, set[str]] = {}
    protected_sources: tuple[tuple[Path, str], ...] = ()
    if layout.project_root is not None:
        assert union is not None
        keep = union.wanted_blocks
        protected_sources = tuple(
            (source, hashlib.sha256(source.read_bytes()).hexdigest())
            for source in dict.fromkeys(
                source for block in union.blocks for source in block.sources
            )
        )
        # Drop only old DSH custody; keep every separately owned Codex block.
        for relative, names in load_local_registry(layout.project_root)[
            "rule_blocks"
        ].items():
            keep.setdefault((layout.project_root / relative).resolve(), set()).update(
                names
            )
        if registry is not None:
            for relative, names in registry.rule_blocks.items():
                keep.setdefault(
                    (layout.project_root / relative).resolve(), set()
                ).update(names)
    for result in install.shared_rules:
        assert result.payload is not None
        keep.setdefault(layout.root_agents_md.resolve(), set()).add(result.payload.name)
        text = (
            layout.root_agents_md.read_text() if layout.root_agents_md.exists() else ""
        )
        if not agents_md.block_matches(result.payload.name, result.payload.body, text):
            drift.append(f"AGENTS.md/{result.payload.name} (missing/source changed)")
    desired_blocks = {
        result.payload.name
        for result in install.shared_rules
        if result.payload is not None
    }
    retired_blocks: dict[Path, set[str]] = {}
    removed: dict[Path, set[str]] = {}
    anchor = layout.project_root or layout.dsh_dir
    for relative, names in previous.rule_blocks.items():
        path = anchor / relative
        if (
            path.name != "AGENTS.md"
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ConfigError(f"Unsafe DSH rule block record: {relative}")
        _guard_destination(layout, path)
        for name in names:
            if path == layout.root_agents_md and name in desired_blocks:
                continue
            body = _block_body(previous, name)
            _verify_block(path, name, body)
            retired_blocks.setdefault(path, set()).add(name)
            if name not in keep.get(path.resolve(), set()):
                removed.setdefault(path, set()).add(name)
            drift.append(f"{relative}/{name} (retired)")
    if set(previous.source_records) != install.current_source_ids:
        drift.append("source contributions changed")
    for rendered in (*install.skills, *install.agents, *install.rules):
        source_provenance = rendered.provenance.as_dict()
        matches = [
            record
            for record in previous.source_records.values()
            if isinstance(record.get("provenance"), dict)
            and all(
                cast(dict[str, object], record["provenance"]).get(key)
                == source_provenance[key]
                for key in ("source", "origin", "element")
            )
        ]
        expected = {
            "generator": DSH_INSTALL_GENERATOR_VERSION,
            "provenance": source_provenance,
            "status": rendered.status,
            "diagnostics": [asdict(item) for item in rendered.diagnostics],
            "source_text": rendered.provenance.source.read_bytes().decode("utf-8"),
        }
        if len(matches) != 1 or any(
            matches[0].get(key) != value for key, value in expected.items()
        ):
            drift.append(
                f"{rendered.provenance.element} (source/generator contribution changed)"
            )
    if registry is not None:
        assert layout.project_root is not None
        if registry != load_dsh_local_registry(layout.project_root):
            drift.append("local source/resource/contribution custody changed")
    guards_paths = [layout.provenance_path, layout.local_registry_path]
    if layout.project_root is not None:
        guards_paths.append(registry_path(layout.project_root))
    guards = tuple((path, _digest(path)) for path in guards_paths)
    return DshReconcilePlan(
        install,
        previous,
        tuple(dict.fromkeys(drift)),
        retired,
        retired_blocks,
        removed,
        refresh_custody,
        guards,
        migration,
        registry,
        protected_sources,
        (
            (*config.diagnostics, *config.permissions.diagnostics, *hooks.diagnostics)
            if migration is None
            else ()
        ),
    )


def apply_dsh_reconciliation(
    plan: DshReconcilePlan, *, check_only: bool = False, strict: bool = False
) -> DshReconcileReport:
    """Recheck all custody and originals before the first mutation."""
    layout = plan.install.layout
    require_admission(
        plan.diagnostics,
        strict=strict or plan.install.strict,
        context="Cannot reconcile DSH activation",
    )
    for path, expected in plan.protected_sources:
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise LinkError(f"Protected shared source changed after planning: {path}")
    for path, expected_registry in plan.guards:
        _guard_destination(layout, path)
        if _digest(path) != expected_registry:
            raise LinkError(f"DSH lifecycle registry changed after planning: {path}")
    if plan.migration is not None:
        verify_dsh_local_inputs(plan.migration.inputs)
    preflight_dsh_install(plan.install, local_rule_custody=plan.local_rule_custody)
    for key in plan.retired_outputs:
        verify_dsh_owned_output(layout, key, inventory=plan.previous)
    for path, names in plan.retired_blocks.items():
        _guard_destination(layout, path)
        for name in names:
            _verify_block(path, name, _block_body(plan.previous, name))
    report = DshReconcileReport(
        list(plan.drift), check_only, diagnostics=plan.diagnostics
    )
    if check_only or not plan.drift:
        return report
    result = apply_dsh_install(
        plan.install, local_rule_custody=plan.local_rule_custody, strict=strict
    )
    changed = list(result.changed_paths)
    for key in plan.retired_outputs:
        path = layout.dsh_dir / key
        if path.is_symlink() or path.is_file():
            path.unlink()
            changed.append(path)
        elif path.is_dir():
            shutil.rmtree(path)
            changed.append(path)
    for path, names in plan.removed_blocks.items():
        if agents_md.remove_rule_blocks(path, names):
            changed.append(path)
    inventory = DshInventory(
        {
            key: value
            for key, value in result.inventory.records.items()
            if key in plan.install.desired_output_keys
        },
        {
            key: value
            for key, value in result.inventory.source_records.items()
            if key in plan.install.current_source_ids
        },
        {
            relative: remaining
            for relative, names in result.inventory.rule_blocks.items()
            if (
                remaining := [
                    name
                    for name in names
                    if name
                    not in plan.retired_blocks.get(
                        (layout.project_root or layout.dsh_dir) / relative, set()
                    )
                ]
            )
        },
        {
            key: value
            for key, value in result.inventory.shared_rule_records.items()
            if cast(dict[str, object], value["source_record"])["name"]
            not in plan.retired_blocks.get(layout.root_agents_md, set())
        },
    )
    data = _inventory_bytes(inventory)
    if layout.provenance_path.read_bytes() != data:
        layout.provenance_path.write_bytes(data)
        changed.append(layout.provenance_path)
    if plan.local_registry is not None:
        assert layout.project_root is not None
        if save_dsh_local_registry(layout.project_root, plan.local_registry):
            changed.append(layout.local_registry_path)
    report.changed_paths = tuple(dict.fromkeys(changed))
    return report


def reconcile_dsh(
    project_root: Path,
    packages: Sequence[str],
    catalog: Path,
    *,
    check_only: bool = False,
    include_catalog: bool = True,
    targets: Sequence[Target] = (Target.DSH,),
    mode: InstallMode = "link",
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
    local_inputs: DshLocalInputs | None = None,
    strict: bool = False,
) -> DshReconcileReport:
    """Refresh/retire one project's catalog and migrated local contributions."""
    return apply_dsh_reconciliation(
        plan_dsh_reconciliation(
            project_layout(project_root),
            packages,
            catalog,
            targets=targets,
            include_catalog=include_catalog,
            mode=mode,
            native_frontmatter=native_frontmatter,
            local_inputs=local_inputs,
            strict=strict,
        ),
        check_only=check_only,
        strict=strict,
    )


def reconcile_dsh_global(
    packages: Sequence[str],
    catalog: Path,
    *,
    check_only: bool = False,
    include_catalog: bool = True,
    configured_home: str | Path | None = None,
    mode: InstallMode = "link",
    native_frontmatter: Mapping[Path, Mapping[str, object]] | None = None,
    strict: bool = False,
) -> DshReconcileReport:
    """User scope visits only recorded outputs and explicit instruction blocks."""
    return apply_dsh_reconciliation(
        plan_dsh_reconciliation(
            global_layout(configured_home),
            packages,
            catalog,
            include_catalog=include_catalog,
            mode=mode,
            native_frontmatter=native_frontmatter,
            strict=strict,
        ),
        check_only=check_only,
        strict=strict,
    )


def prune_dsh(
    plan: DshReconcilePlan, *, check_only: bool = False
) -> DshReconcileReport:
    """Apply the same fresh desired/protected union; unrecorded files are untouched."""
    return apply_dsh_reconciliation(plan, check_only=check_only)
