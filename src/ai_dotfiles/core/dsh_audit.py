"""Versioned data and shipped modules for the pinned native DSH boundary.

Collectors merge global/project sources before calling ``build_bridge_config``.
Only READY render results and an unblocked original-source permission policy
may activate. A bridge row passes this object as its native ``config``; an audit
row passes ``DshAuditRequirements.as_dict()``. Both modules are import-free ESM
Cordis plugins with named ``name``, ``inject`` and ``apply`` exports.

After native boot, the host MUST await ``ctx.aiDotfilesAudit.run({scope})`` (or
``auditReady(ctx, config, {scope})``) for the chosen native Agent composition
before launching a surface. Preset-based profiles without a chosen scope fail
with COMPOSITION_NOT_SELECTED; a global-only profile needs no scope argument.
The plugin's synchronous apply only exposes that boundary: awaiting Loader
inside its own apply deadlocks. Native exit 0 is not an audit result. The audit
checks the settled root Loader and selected native preset tree by Entry identity,
including all required managed rows and their optional failures, every id,
service/tool/provider and the bridge's final assembled prompt. Complete persona
modes fail rather than losing the literal sections after native assembly.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from importlib import resources
from typing import TypedDict, cast

from ai_dotfiles.core.dsh_permissions import (
    DshPermissionBridgeData,
    DshPermissionPolicy,
)
from ai_dotfiles.core.dsh_render import (
    DshAgentPayload,
    DshRenderResult,
    DshRulePayload,
)
from ai_dotfiles.core.errors import ConfigError

DSH_BRIDGE_SCHEMA_VERSION = 1
DSH_BRIDGE_GENERATOR_VERSION = 1
DSH_AUDIT_SCHEMA_VERSION = 1
DSH_AUDIT_GENERATOR_VERSION = 2
DSH_BRIDGE_ROW_ID = "ai-dotfiles-bridge"
DSH_AUDIT_ROW_ID = "ai-dotfiles-audit"
_EMPTY_PERMISSIONS = DshPermissionPolicy()


class DshBridgeConfig(TypedDict):
    schemaVersion: int
    generator: int
    agents: list[dict[str, object]]
    rules: list[dict[str, object]]
    permissions: DshPermissionBridgeData


class DshAuditConfig(TypedDict):
    schemaVersion: int
    generator: int
    requiredIds: list[str]
    requiredTools: list[str]
    requiredServices: list[str]
    requiredSubagentProviders: list[str]


@dataclass(frozen=True)
class DshAuditRequirements:
    """Explicit capabilities; missing/disabled rows never count as readiness.

    Ids are configured leaf row ids or qualified native ``Entry.id`` values;
    native mountRootInclude prefixes root rows with ``include:``. The audit
    requires exactly one match, so duplicate leaf ids cannot pass. Pass all
    managed ids, including bridge and audit rows. Tools include agent allow
    AND deny filters and the complete
    permission required_tools, including conditional read_image. Native providers
    are names registered on subagents, e.g. ``spawn``; services are Cordis keys.
    Additional skill/MCP/hooks providers belong to their producers' requirements.
    """

    required_ids: tuple[str, ...] = (DSH_BRIDGE_ROW_ID, DSH_AUDIT_ROW_ID)
    required_tools: tuple[str, ...] = ()
    required_services: tuple[str, ...] = ("systemPrompt", "tools", "aiDotfilesBridge")
    required_subagent_providers: tuple[str, ...] = ()

    def as_dict(self) -> DshAuditConfig:
        """Return native JSON config without dropping any required capability."""
        values = (
            self.required_ids,
            self.required_tools,
            self.required_services,
            self.required_subagent_providers,
        )
        if any(not isinstance(item, str) or not item for seq in values for item in seq):
            raise ConfigError("DSH audit requirements need non-empty native names")
        return {
            "schemaVersion": DSH_AUDIT_SCHEMA_VERSION,
            "generator": DSH_AUDIT_GENERATOR_VERSION,
            "requiredIds": sorted(set(self.required_ids)),
            "requiredTools": sorted(set(self.required_tools)),
            "requiredServices": sorted(set(self.required_services)),
            "requiredSubagentProviders": sorted(set(self.required_subagent_providers)),
        }


def _ready[T](result: DshRenderResult[T]) -> T:
    if result.status != "READY" or result.payload is None:
        raise ConfigError(
            f"Cannot activate DSH {result.provenance.element}: {result.status}; "
            + "; ".join(item.reason for item in result.diagnostics)
        )
    return result.payload


def build_bridge_config(
    agents: Iterable[DshRenderResult[DshAgentPayload]] = (),
    rules: Iterable[DshRenderResult[DshRulePayload]] = (),
    *,
    permissions: DshPermissionPolicy = _EMPTY_PERMISSIONS,
) -> DshBridgeConfig:
    """Join already precedence-resolved READY data; never merge source settings.

    Agent records extend renderer bridge_data with ``rowId``, ``requiredTools``
    and exact ``toolFilter``/``agentOptions`` snapshots. Missing snapshots are
    null; an explicit empty allow list retains its distinct restriction. Their
    description/persona/sourceModel/provenance remain exact. Only literal rules
    enter this private bridge; shared rules belong in
    AGENTS.md. Duplicate names are an unresolved collector collision, not a cue
    to rename/overwrite. JSON source parsing belongs to the collector and must
    reject before this function; an invalid source is never an empty policy.
    """
    if permissions.blocked:
        raise ConfigError(
            "Cannot activate blocked DSH permissions: "
            + "; ".join(
                f"{item.origin} {item.field}: {item.reason}"
                for item in permissions.diagnostics
                if item.blocking
            )
        )
    agent_data: list[dict[str, object]] = []
    rule_data: list[dict[str, object]] = []
    names: set[str] = set()
    for result in agents:
        agent = _ready(result)
        if agent.name in names:
            raise ConfigError(f"Duplicate managed DSH agent: {agent.name}")
        names.add(agent.name)
        agent_data.append(
            {
                **agent.bridge_data(result.provenance),
                "rowId": agent.row["id"],
                "requiredTools": list(agent.required_tools),
                "toolFilter": deepcopy(agent.row["config"].get("toolFilter")),
                "agentOptions": deepcopy(agent.row["config"].get("agentOptions")),
            }
        )
    names.clear()
    for rule_result in rules:
        rule = _ready(rule_result)
        if rule.activation != "literal":
            raise ConfigError(f"Shared DSH rule {rule.name} belongs in AGENTS.md")
        if rule.name in names:
            raise ConfigError(f"Duplicate managed DSH literal rule: {rule.name}")
        names.add(rule.name)
        rule_data.append(rule.bridge_data(rule_result.provenance))
    return {
        "schemaVersion": DSH_BRIDGE_SCHEMA_VERSION,
        "generator": DSH_BRIDGE_GENERATOR_VERSION,
        "agents": agent_data,
        "rules": rule_data,
        "permissions": permissions.bridge_data(),
    }


def bridge_audit_requirements(
    config: DshBridgeConfig,
    *,
    required_ids: Iterable[str] = (),
    required_tools: Iterable[str] = (),
    required_services: Iterable[str] = (),
    required_subagent_providers: Iterable[str] = (),
) -> DshAuditRequirements:
    """Accumulate bridge requirements with all producers' native requirements.

    This accepts output of build_bridge_config, not arbitrary decoded input.
    Collector/native-helper requirements must include provider row ids as well
    as service/capability names; an active service alone does not prove its
    managed contribution activated. Scoped composition stays native.
    """
    ids = {DSH_BRIDGE_ROW_ID, DSH_AUDIT_ROW_ID, *required_ids}
    tools = {*config["permissions"]["requiredTools"], *required_tools}
    services = {"systemPrompt", "tools", "aiDotfilesBridge", *required_services}
    providers = set(required_subagent_providers)
    for agent in config["agents"]:
        ids.add(str(agent["rowId"]))
        tools.add(str(agent["toolName"]))
        tools.update(cast(list[str], agent["requiredTools"]))
    if config["agents"]:
        services.update(("agents", "agentLoop", "llm", "subagents"))
        providers.add("spawn")
    if config["permissions"]["ask"]:
        services.add("approval")
    return DshAuditRequirements(
        tuple(sorted(ids)),
        tuple(sorted(tools)),
        tuple(sorted(services)),
        tuple(sorted(providers)),
    )


def _module_text(template: str, kind: str, generator: int) -> str:
    source = resources.files("ai_dotfiles.scaffold.templates").joinpath(template)
    try:
        body = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(
            f"Cannot read shipped DSH template {template} at {source}: {exc}; "
            "reinstall ai-dotfiles to restore its packaged templates"
        ) from exc
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        f"// ai-dotfiles:managed dsh-{kind}\n"
        f"// source-sha256: {digest}\n// generator: {generator}\n" + body
    )


def bridge_module_text() -> str:
    """Materialize the shipped ESM with template SHA/generator ownership."""
    return _module_text("dsh_bridge.mjs", "bridge", DSH_BRIDGE_GENERATOR_VERSION)


def audit_module_text() -> str:
    """Materialize the shipped ESM; it never installs a native runtime/package."""
    return _module_text("dsh_audit.mjs", "audit", DSH_AUDIT_GENERATOR_VERSION)
