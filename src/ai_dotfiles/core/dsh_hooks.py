"""Original command-hook sources -> one native config and owned resource plan.

The pinned plugin is a partial protocol adapter, not a Claude hook engine. This
collector validates before its lenient parser can silently ignore a restriction.
It never executes/rewrites script bodies, infers their output, merges Claude
settings, or deduplicates handlers. Required semantics are evidence supplied by
the migration caller, not a new source format or CLI option.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from ai_dotfiles.core.dsh_admission import require_admission, skipped_diagnostics
from ai_dotfiles.core.dsh_audit import DshAuditRequirements
from ai_dotfiles.core.dsh_config import DshConfigSource, DshNativeContribution
from ai_dotfiles.core.dsh_install import (
    DshInstallPlan,
    DshOutput,
    DshResource,
    plan_dsh_install,
)
from ai_dotfiles.core.dsh_layout import DshLayout
from ai_dotfiles.core.dsh_render import (
    DshDiagnostic,
    DshProvenance,
    native_tool_names,
)
from ai_dotfiles.core.errors import ConfigError

if TYPE_CHECKING:
    from ai_dotfiles.core.dsh_migrate import DshLocalSource


DSH_HOOKS_GENERATOR_VERSION = 3
DSH_HOOKS_SCHEMA_VERSION = 1
DSH_HOOKS_PACKAGE = "@deepseek-ai/dsh-hooks-claude-code"
DSH_HOOKS_ROW_ID = "ai-dotfiles-hooks"
SUPPORTED_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStart",
    "SubagentStop",
)
Scope = Literal["global", "project"]
_TOOL_EVENTS = {"PreToolUse", "PostToolUse"}
_SESSION_SOURCES = {"startup", "resume", "clear", "compact"}
_COMMON_LIMITS = {
    "transcript_path": "transcript_path is always empty; no readable transcript file",
    "payload.common": "prompt_id, permission_mode and effort are omitted",
    "systemMessage": "systemMessage is logged but is not surfaced",
    "continue:false": "continue:false is recorded but does not halt the run",
    "suppressOutput": "suppressOutput is not applied",
    "stopReason": "stopReason is not applied as a run-level halt",
    "terminalSequence": "terminalSequence is not applied",
    "execution": (
        "hooks run serially without deduplication; config loads once per process"
    ),
}
_EVENT_LIMITS: dict[str, dict[str, str]] = {
    "SessionStart": {
        "stdout": (
            "plain stdout context is not injected; "
            "use event-keyed JSON additionalContext"
        ),
        "initialUserMessage": "initialUserMessage is not applied",
        "sessionTitle": "sessionTitle is not applied",
        "watchPaths": "watchPaths is not applied",
        "reloadSkills": "reloadSkills is not applied",
        "CLAUDE_ENV_FILE": "CLAUDE_ENV_FILE is not provided",
        "delivery": "lifecycle context is not a guaranteed first-request delivery gate",
        "payload": "model, agent_type and session_title are omitted",
    },
    "UserPromptSubmit": {
        "stdout": (
            "plain stdout context is not injected; "
            "use event-keyed JSON additionalContext"
        ),
        "sessionTitle": "sessionTitle is not applied",
        "suppressOriginalPrompt": "suppressOriginalPrompt is not applied",
        "timeout": (
            "an omitted timeout uses native 600 seconds, "
            "not the Claude event-specific 30 seconds"
        ),
    },
    "PreToolUse": {
        "updatedInput": "updatedInput is logged but does not rewrite tool input",
        "additionalContext": "PreToolUse additionalContext is ignored",
        "permissionDecision.allow": "allow does not pre-approve the tool",
        "permissionDecision.defer": "defer is unsupported",
    },
    "PostToolUse": {
        "updatedToolOutput": "updatedToolOutput is not applied",
        "updatedMCPToolOutput": "updatedMCPToolOutput is not applied",
        "tool_response": (
            "tool_response is flattened text, not original structured tool output"
        ),
    },
    "Stop": {
        "stop_hook_active": (
            "stop_hook_active is always false; no consecutive-block cap"
        ),
        "payload": (
            "last_assistant_message, background_tasks and session_crons are omitted"
        ),
    },
    "SubagentStart": {
        "agent_type": (
            "agent_type is the constant general-purpose, not a named child type"
        ),
        "session_id": "session_id identifies the child, not the parent",
        "delivery": "context is best-effort and reaches only a live in-process child",
    },
    "SubagentStop": {
        "agent_type": (
            "agent_type is the constant general-purpose, not a named child type"
        ),
        "session_id": "session_id identifies the child, not the parent",
        "decision": "SubagentStop is observe-only; it cannot block or add context",
        "additionalContext": "SubagentStop cannot add context",
        "exit-2": "SubagentStop is observe-only; exit 2 cannot block a child",
        "stop_hook_active": "stop_hook_active is always false",
        "payload": (
            "agent_transcript_path, last_assistant_message, "
            "background_tasks and session_crons are omitted"
        ),
    },
}
# Recognize only a launch target, optionally after a known interpreter. This is
# not a shell parser: literal arguments and later shell fragments remain exact.
_LAUNCH = re.compile(
    r"\A(?P<prefix>\s*(?:(?:/bin/|/usr/bin/)?(?:bash|sh|python3?|node)\s+)?)"
    r"(?P<target>\"[^\"\n]+\"|'[^'\n]+'|[^\s;&|<>]+)"
)
# Exact reviewed stock sources, not a filename/command-based hook exemption.
_GITFLOW_SCRIPT_SHA = "4289082608856bca6735d552f4394654e79271d07d5d689b7d209ff1180386b6"
_GITFLOW_RULE_SHA = "4654745ce9729e280cfecefa2991e6781d4d78a90789f1ea24620880d2363a87"
_GITFLOW_AGENT_SHA = "2b27ba39b6ef359af22bb0c8ee439ba751a4d48db6a05e3213ab3d5e222651e3"


def _gitflow_policy_fallback(
    source: DshHookSource, plans: Sequence[DshInstallPlan]
) -> tuple[tuple[DshProvenance, ...], str | None]:
    """Prove selected stock sources and the same precedence used by composition.

    Only the reviewed no-path rule and inherited-model agent qualify. Runtime
    delivery is still required by the existing bridge's selected-tree audit;
    source readiness alone never releases a native surface.
    """
    root = source.path.parent.absolute()
    if (
        source.origin != "@gitflow"
        or source.element != "@gitflow"
        or source.path.name != "settings.fragment.json"
        or source.source_root is None
        or source.source_root.absolute() != root
        or source.local_source is not None
        or source.required_semantics
    ):
        return (), "selected stock catalog origin is unproven"
    ordered = sorted(plans, key=lambda plan: plan.layout.project_root is not None)
    matching = [
        plan
        for plan in ordered
        if ("project" if plan.layout.project_root is not None else "global")
        == source.scope
        and any(
            resource.source.absolute() == root
            and resource.relative_path == Path("domains/gitflow")
            and resource.provenance.origin == "@gitflow"
            and resource.provenance.element == "@gitflow"
            for resource in plan.resources
        )
    ]
    if len(matching) != 1:
        return (), "selected stock catalog resource is unproven"
    script = root / "hooks/route-to-agent.sh"
    try:
        digest = hashlib.sha256(_read(script)).hexdigest()
    except ConfigError:
        return (), "stock context-only script is unavailable"
    if digest != _GITFLOW_SCRIPT_SHA:
        return (), "context-only script differs from the reviewed stock bytes"
    agents = {
        result.payload.name: result
        for plan in ordered
        for result in plan.ready_agents
        if result.payload is not None
    }
    rules = {
        result.payload.name: result
        for plan in ordered
        for result in plan.literal_rules
        if result.payload is not None
    }
    rule = rules.get("gitflow")
    agent = agents.get("git-workflow-assistant")
    for result, relative, expected, label in (
        (rule, "rules/gitflow.md", _GITFLOW_RULE_SHA, "always-on routing rule"),
        (
            agent,
            "agents/git-workflow-assistant.md",
            _GITFLOW_AGENT_SHA,
            "callable inherited-model agent",
        ),
    ):
        if (
            result is None
            or result.provenance.source.absolute() != root / relative
            or result.provenance.origin != "@gitflow"
            or result.provenance.element != "@gitflow/" + relative
            or result.provenance.source_sha256 != expected
            or hashlib.sha256(_read(result.provenance.source)).hexdigest() != expected
        ):
            return (), f"effective stock {label} is unavailable or changed"
    assert rule is not None and agent is not None and agent.payload is not None
    # dsh_render.render_agent / DSH_RENDER_GENERATOR_VERSION (currently 1)
    # define this callable inherited-model shape. Renderer shape/version changes
    # require fallback/native proof re-review; keep unknown config keys rejected.
    if agent.payload.row["config"] != {
        "provider": "spawn",
        "toolName": "ai_dotfiles_agent_git-workflow-assistant",
        "persona": agent.payload.persona,
    }:
        return (), "stock agent does not retain its callable inherited-model route"
    return (
        DshProvenance(
            script,
            "@gitflow",
            "@gitflow/hooks/route-to-agent.sh",
            digest,
            DSH_HOOKS_GENERATOR_VERSION,
        ),
        rule.provenance,
        agent.provenance,
    ), None


@dataclass(frozen=True)
class DshHookSource:
    """One original settings/hooks file and explicit source-origin directory.

    An omitted source_root binds only the known hooks/ subtree beside the input,
    never copies the parent .claude/home/project tree. An explicit source_root
    declares a bounded complete domain/plugin support bundle. binding_root must
    be under the output layout's resources_dir; catalog domain roots are reused.
    required_semantics names observed requirements (e.g. updatedInput), not
    inferred shell behavior. Bare event maps and settings hooks are both accepted.
    """

    path: Path
    scope: Scope
    origin: str
    element: str
    source_root: Path | None = None
    binding_root: Path | None = None
    required_semantics: tuple[str, ...] = ()
    local_source: DshLocalSource | None = None


@dataclass(frozen=True)
class DshHookPlan:
    """Read-only original records, combined groups and source-backed resources."""

    layout: DshLayout
    project_root: Path | None
    sources: tuple[dict[str, object], ...]
    hooks: dict[str, list[dict[str, object]]]
    resources: tuple[DshResource, ...]
    resource_outputs: tuple[DshOutput, ...]
    provenance: tuple[DshProvenance, ...]
    diagnostics: tuple[DshDiagnostic, ...]
    local_sources: tuple[DshLocalSource, ...] = ()

    @property
    def blocked(self) -> bool:
        return any(item.blocking for item in self.diagnostics)

    @property
    def skipped(self) -> tuple[DshDiagnostic, ...]:
        return skipped_diagnostics(self.diagnostics)

    @property
    def partial(self) -> bool:
        return bool(self.skipped)

    def require_activatable(self, *, strict: bool = True) -> None:
        """Never activate a partial mandatory guard after ignoring its options."""
        require_admission(
            self.diagnostics, strict=strict, context="Cannot activate MANUAL DSH hooks"
        )

    def contribution(self, *, strict: bool = True) -> DshNativeContribution | None:
        """ONE logical contribution after merging every original scope/domain.

        Omitted projectDir lets a global plan bind to the native session's
        workspace. Managed launch supplies its actual project_root explicitly.
        """
        self.require_activatable(strict=strict)
        if not self.hooks:
            return None
        config: dict[str, object] = {
            "configPath": str(self.layout.hooks_path.absolute())
        }
        if self.project_root is not None:
            config["projectDir"] = str(self.project_root.absolute())
        return DshNativeContribution(
            "hooks",
            "project" if self.project_root is not None else "global",
            ({"id": DSH_HOOKS_ROW_ID, "name": DSH_HOOKS_PACKAGE, "config": config},),
            self.provenance,
            DshAuditRequirements(
                (DSH_HOOKS_ROW_ID,), (), ("shell", "sessionProjections"), ()
            ),
        )

    def output(self, *, strict: bool = True) -> DshOutput:
        """One owned native file also retaining raw originals and diagnostics."""
        self.require_activatable(strict=strict)
        return DshOutput(
            self.layout.hooks_path,
            "generated",
            self.provenance,
            {"hooks": DSH_HOOKS_GENERATOR_VERSION},
            content=_json(
                {
                    "hooks": self.hooks,
                    "aiDotfiles": {
                        "schemaVersion": DSH_HOOKS_SCHEMA_VERSION,
                        "generator": DSH_HOOKS_GENERATOR_VERSION,
                        "sources": deepcopy(list(self.sources)),
                        "diagnostics": [asdict(item) for item in self.diagnostics],
                    },
                }
            ),
        )


def _json(value: object) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"DSH hooks require finite JSON data: {exc}") from exc


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ConfigError(
            f"Cannot read original DSH hooks source {path}: {exc}"
        ) from exc


def _gap(
    source: DshHookSource, field: str, reason: str, *, blocking: bool = True
) -> DshDiagnostic:
    return DshDiagnostic(
        "HOOK_UNMAPPED" if blocking else "HOOK_NATIVE_LIMITATION",
        source.origin,
        source.element,
        field,
        reason,
        blocking,
    )


def _source(
    source: DshHookSource | DshConfigSource, layout: DshLayout
) -> DshHookSource:
    if isinstance(source, DshConfigSource):
        binding = source.binding_root.absolute()
        return DshHookSource(
            source.path,
            source.scope,
            source.origin,
            source.element,
            source_root=(
                source.path.parent
                if source.binding_root.parent.name == "domains"
                and source.path.name == "settings.fragment.json"
                else None
            ),
            local_source=source.local_source,
            binding_root=(
                binding
                if binding.is_relative_to(layout.resources_dir.absolute())
                else None
            ),
        )
    return source


def _binding(source: DshHookSource, layout: DshLayout) -> tuple[Path, Path]:
    root = (source.source_root or source.path.parent).absolute()
    if not source.path.absolute().is_relative_to(root):
        raise ConfigError(
            f"Hook source {source.path} is outside its origin root {root}"
        )
    identity = hashlib.sha256(str(root).encode()).hexdigest()
    binding = (
        source.binding_root or layout.resources_dir / "hook-origins" / identity
    ).absolute()
    if not binding.is_relative_to(layout.resources_dir.absolute()):
        raise ConfigError(f"Hook binding is outside owned resources: {binding}")
    if source.source_root is not None and binding.is_relative_to(root):
        raise ConfigError(f"Hook resource origin contains its destination: {root}")
    relative = binding.relative_to(layout.resources_dir.absolute())
    if not relative.parts or ".." in relative.parts:
        raise ConfigError(f"Unsafe DSH hook resource binding: {binding}")
    return root, binding


def _matcher(event: str, matcher: object) -> str | None:
    if matcher is None or matcher in ("", "*"):
        return matcher
    if not isinstance(matcher, str):
        raise ConfigError("matcher must be a string")
    if event in ("UserPromptSubmit", "Stop"):
        raise ConfigError(f"{event} ignores matchers; cannot preserve this constraint")
    parts = matcher.split("|")
    if event in _TOOL_EVENTS:
        mapped: list[str] = []
        for part in parts:
            names = native_tool_names(part)
            if names is None:
                raise ConfigError(f"unknown/non-exact Claude tool matcher {part!r}")
            mapped.extend(names)
        return "|".join(dict.fromkeys(mapped))
    allowed = _SESSION_SOURCES if event == "SessionStart" else {"general-purpose"}
    if not set(parts) <= allowed:
        raise ConfigError(f"unrepresentable {event} matcher {matcher!r}")
    # Hyphen-bearing strings enter native regex mode; anchors preserve exactness.
    return "^(?:" + "|".join(re.escape(part) for part in parts) + ")$"


def _bind_command(
    command: str, root: Path, binding: Path, *, complete_root: bool, scope: Scope
) -> str:
    match = _LAUNCH.match(command)
    if match is None:
        return command
    target = match["target"]
    path = target[1:-1] if target.startswith(("'", '"')) else target
    relative: str | None = None
    for prefix in (
        "${CLAUDE_PLUGIN_ROOT}/",
        "$CLAUDE_PLUGIN_ROOT/",
        str(root) + "/",
    ):
        if path.startswith(prefix):
            relative = path[len(prefix) :]
            break
    if relative is None:
        for prefix in (
            "${CLAUDE_PROJECT_DIR}/.claude/hooks/",
            "$CLAUDE_PROJECT_DIR/.claude/hooks/",
            "./.claude/hooks/",
            ".claude/hooks/",
            "./hooks/",
            "hooks/",
            *(
                ("${HOME}/.claude/hooks/", "$HOME/.claude/hooks/", "~/.claude/hooks/")
                if scope == "global"
                else ()
            ),
        ):
            if path.startswith(prefix):
                relative = "hooks/" + path[len(prefix) :]
                break
    if relative is not None:
        part = Path(relative)
        if not complete_root and (not part.parts or part.parts[0] != "hooks"):
            raise ConfigError(
                "handler needs an explicit bounded plugin/domain resource root"
            )
        if part.is_absolute() or ".." in part.parts or not (root / part).is_file():
            raise ConfigError(
                f"unavailable/unsafe origin-bound handler resource {relative!r}"
            )
        command = (
            command[: match.start("target")]
            + shlex.quote(str(binding / part))
            + command[match.end("target") :]
        )
    # No global string replacement: a plugin root or Claude-install path in a
    # later shell expression cannot be proved without interpreting that shell.
    if "CLAUDE_PLUGIN_ROOT" in command or ".claude/hooks/" in command:
        raise ConfigError(
            "unbound origin resource outside a recognized launch target; "
            "manual adaptation required"
        )
    return command


def _required_reason(event: str, semantic: str) -> str | None:
    limits = {**_COMMON_LIMITS, **_EVENT_LIMITS[event]}
    if semantic in limits:
        return limits[semantic]
    supported = {"command", "timeout"}
    if event in {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}:
        supported.add("exit-2")
    if event in {"SessionStart", "UserPromptSubmit", "PostToolUse", "SubagentStart"}:
        supported.add("additionalContext")
    if event == "PreToolUse":
        supported.update(("permissionDecision.deny", "permissionDecision.ask"))
    if event == "Stop":
        supported.add("Stop.block")
    return (
        None
        if semantic in supported
        else f"required semantic {semantic!r} is not proven by the pinned native plugin"
    )


def _handler(
    source: DshHookSource,
    event: str,
    field: str,
    handler: object,
    root: Path,
    binding: Path,
    diagnostics: list[DshDiagnostic],
) -> dict[str, object] | None:
    start = len(diagnostics)
    if not isinstance(handler, dict):
        diagnostics.append(_gap(source, field, "handler must be an object"))
        return None
    if handler.get("type", "command") != "command":
        diagnostics.append(
            _gap(source, field + ".type", "only shell-form command handlers run")
        )
    for key in handler.keys() - {"type", "command", "timeout"}:
        diagnostics.append(
            _gap(
                source,
                field + "." + key,
                f"native command parser ignores handler option {key!r}",
            )
        )
    command = handler.get("command")
    native: dict[str, object] = {"type": "command"}
    if not isinstance(command, str) or not command.strip():
        diagnostics.append(
            _gap(source, field + ".command", "command must be a non-empty string")
        )
    else:
        try:
            native["command"] = _bind_command(
                command,
                root,
                binding,
                complete_root=source.source_root is not None,
                scope=source.scope,
            )
        except ConfigError as exc:
            diagnostics.append(_gap(source, field + ".command", str(exc)))
    if "timeout" in handler:
        timeout = handler["timeout"]
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            diagnostics.append(
                _gap(
                    source,
                    field + ".timeout",
                    "timeout must be positive finite seconds",
                )
            )
        else:
            native["timeout"] = timeout
    for semantic in source.required_semantics:
        reason = _required_reason(event, semantic)
        if reason is not None:
            diagnostics.append(_gap(source, field + ".required." + semantic, reason))
    if any(item.blocking for item in diagnostics[start:]):
        return None
    for key, reason in {**_COMMON_LIMITS, **_EVENT_LIMITS[event]}.items():
        diagnostics.append(
            _gap(source, field + ".native." + key, reason, blocking=False)
        )
    return native


def collect_dsh_hooks(
    sources: Iterable[DshHookSource | DshConfigSource],
    layout: DshLayout,
    *,
    project_root: Path | None = None,
    install_plans: Sequence[DshInstallPlan] = (),
) -> DshHookPlan:
    """Combine originals global-first, preserving source order and repeats.

    Explicit bounded catalog/plugin origins reuse or copy their complete resource
    tree. Implicit local/global origins retain the raw input and only a referenced
    hooks/ subtree, without copying the parent directory. No installed Claude tree
    or earlier global install is needed. Other config source kinds are ignored.
    Malformed source JSON raises before any native use.
    """
    ordered = sorted(
        (
            _source(item, layout)
            for item in sources
            if not isinstance(item, DshConfigSource) or item.kind == "settings"
        ),
        key=lambda item: item.scope == "project",
    )
    records: list[dict[str, object]] = []
    hooks: dict[str, list[dict[str, object]]] = {}
    resources: dict[Path, DshResource] = {}
    provenance: list[DshProvenance] = []
    diagnostics: list[DshDiagnostic] = []
    for source in ordered:
        if source.scope not in ("global", "project"):
            raise ConfigError(f"Unknown DSH hook source scope: {source.scope}")
        raw = _read(source.path)
        try:
            value = json.loads(raw)
            _json(value)
        except (ValueError, UnicodeError) as exc:
            raise ConfigError(
                f"Invalid original DSH hook JSON {source.path}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise ConfigError(
                f"Original DSH hooks source must be an object: {source.path}"
            )
        if source.local_source is not None:
            from ai_dotfiles.core.dsh_migrate import read_dsh_local_source

            if (
                layout.project_root is None
                or source.scope != "project"
                or source.origin != "local"
                or source.path != source.local_source.path
                or source.local_source.kind not in ("hooks", "settings")
                or source.element != source.local_source.provenance.element
                or source.source_root is not None
                or source.binding_root is not None
            ):
                raise ConfigError(
                    f"Invalid local DSH hook source identity: {source.path}"
                )
            value = read_dsh_local_source(layout.project_root, source.local_source)
        root, binding = _binding(source, layout)
        part = DshProvenance(
            source.path,
            source.origin,
            source.element,
            hashlib.sha256(raw).hexdigest(),
            DSH_HOOKS_GENERATOR_VERSION,
        )
        provenance.append(part)
        start = len(diagnostics)
        record: dict[str, object] = {
            **part.as_dict(),
            "scope": source.scope,
            "sourceRoot": str(root),
            "bindingRoot": str(binding),
            "requiredSemantics": list(source.required_semantics),
            "value": deepcopy(value),
        }
        records.append(record)
        if "hooks" in value:
            event_map = value["hooks"]
        elif isinstance(source, DshHookSource) and source.path.name == "hooks.json":
            event_map = value
        else:
            event_map = {}
        if not isinstance(event_map, dict):
            diagnostics.append(
                _gap(source, "hooks", "hooks must map event names to group arrays")
            )
            record["status"] = "MANUAL"
            continue
        # Standalone input gets its own guarded original copy too, independently
        # of whether an existing install plan already includes the origin tree.
        identity = hashlib.sha256(str(source.path.absolute()).encode()).hexdigest()
        raw_resource = DshResource(
            source.path, Path("hook-sources") / (identity + ".json"), part
        )
        resources.setdefault(
            layout.resources_dir.absolute() / raw_resource.relative_path, raw_resource
        )
        for event, groups in event_map.items():
            field = "hooks." + event
            if event not in SUPPORTED_EVENTS:
                diagnostics.append(_gap(source, field, "unsupported native hook event"))
                continue
            if not isinstance(groups, list):
                diagnostics.append(_gap(source, field, "event groups must be an array"))
                continue
            for index, group in enumerate(groups):
                group_field = f"{field}[{index}]"
                group_start = len(diagnostics)
                if not isinstance(group, dict):
                    diagnostics.append(
                        _gap(source, group_field, "matcher group must be an object")
                    )
                    continue
                for key in group.keys() - {"matcher", "hooks"}:
                    diagnostics.append(
                        _gap(
                            source,
                            group_field + "." + key,
                            "native parser ignores this group option",
                        )
                    )
                try:
                    if "matcher" in group and group["matcher"] is None:
                        raise ConfigError("an explicit matcher must be a string")
                    matcher = _matcher(event, group.get("matcher"))
                except ConfigError as exc:
                    diagnostics.append(_gap(source, group_field + ".matcher", str(exc)))
                    matcher = None
                handlers = group.get("hooks")
                if not isinstance(handlers, list):
                    diagnostics.append(
                        _gap(
                            source, group_field + ".hooks", "handlers must be an array"
                        )
                    )
                    continue
                valid_group = not any(
                    item.blocking for item in diagnostics[group_start:]
                )
                translated = []
                for number, handler in enumerate(handlers):
                    handler_field = f"{group_field}.hooks[{number}]"
                    if (
                        valid_group
                        and event == "PreToolUse"
                        and group.get("matcher") == "Bash"
                        and isinstance(handler, dict)
                        and handler.get("if") in ("Bash(git *)", "Bash(gh *)")
                        and handler
                        == {
                            "type": "command",
                            "if": handler["if"],
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/"
                            "route-to-agent.sh",
                        }
                    ):
                        evidence, reason = _gitflow_policy_fallback(
                            source, install_plans
                        )
                        if reason is None:
                            provenance.extend(evidence)
                            diagnostics.append(
                                DshDiagnostic(
                                    "HOOK_GITFLOW_POLICY_FALLBACK",
                                    source.origin,
                                    source.element,
                                    handler_field,
                                    "Retired verified stock context-only reminder; "
                                    "the always-on gitflow routing policy and "
                                    "callable ai_dotfiles_agent_git-workflow-assistant "
                                    "remain required by managed native audit. "
                                    "The per-command hook nudge is absent: DSH "
                                    "ignores PreToolUse additionalContext and if "
                                    "is not translated",
                                    False,
                                )
                            )
                            continue
                        diagnostics.append(
                            _gap(
                                source,
                                handler_field + ".if",
                                "Stock gitflow policy fallback unavailable: "
                                + reason
                                + "; restore the stock sources and native rule/"
                                "agent delivery, or adapt this hook manually",
                            )
                        )
                        continue
                    native = _handler(
                        source,
                        event,
                        handler_field,
                        handler,
                        root,
                        binding,
                        diagnostics,
                    )
                    if native is not None:
                        translated.append(native)
                        original = cast(dict[str, object], handler)["command"]
                        if native["command"] != original:
                            resource_root = (
                                root
                                if source.source_root is not None
                                else root / "hooks"
                            )
                            resource_binding = (
                                binding
                                if source.source_root is not None
                                else binding / "hooks"
                            )
                            resource = DshResource(
                                resource_root,
                                resource_binding.relative_to(
                                    layout.resources_dir.absolute()
                                ),
                                part,
                            )
                            previous = resources.get(resource_binding)
                            if (
                                previous is not None
                                and previous.source != resource_root
                            ):
                                raise ConfigError(
                                    "Different hook origins share resource binding "
                                    f"{resource_binding}"
                                )
                            resources.setdefault(resource_binding, resource)
                if translated and valid_group:
                    native_group: dict[str, object] = {"hooks": translated}
                    if matcher is not None:
                        native_group["matcher"] = matcher
                    hooks.setdefault(event, []).append(native_group)
        record["status"] = (
            "MANUAL" if any(item.blocking for item in diagnostics[start:]) else "READY"
        )
    planned = plan_dsh_install(layout, resources=resources.values())
    resource_paths = {
        layout.resources_dir / item.relative_path for item in resources.values()
    }
    return DshHookPlan(
        layout,
        project_root or layout.project_root,
        tuple(records),
        hooks,
        tuple(resources.values()),
        tuple(item for item in planned.outputs if item.path in resource_paths),
        tuple(dict.fromkeys(provenance)),
        tuple(diagnostics),
        tuple(
            source.local_source for source in ordered if source.local_source is not None
        ),
    )


def attach_dsh_hook_outputs(
    install: DshInstallPlan, hooks: DshHookPlan, *, strict: bool = True
) -> DshInstallPlan:
    """Add complete resource/source preflight and ONE hooks output, without writes.

    Preserve every existing output, local protection and contribution. Source
    digests are checked before acquiring fresh resource inventories, so a changed
    original cannot be authorized as if it were the input that was validated.
    """
    if install.layout != hooks.layout:
        raise ConfigError("DSH hook and install output layouts differ")
    hooks.require_activatable(strict=strict)
    if hooks.local_sources:
        from ai_dotfiles.core.dsh_migrate import read_dsh_local_source

        assert hooks.layout.project_root is not None
        for source in hooks.local_sources:
            read_dsh_local_source(hooks.layout.project_root, source)
    for part in hooks.provenance:
        if hashlib.sha256(_read(part.source)).hexdigest() != part.source_sha256:
            raise ConfigError(f"DSH hook source changed after planning: {part.source}")
    resources = list(install.resources)
    known = {item.relative_path: item for item in resources}
    for resource in hooks.resources:
        previous = known.get(resource.relative_path)
        if previous is not None:
            if (
                previous.source.absolute() != resource.source.absolute()
                or previous.mode != resource.mode
            ):
                raise ConfigError(
                    f"Conflicting DSH hook resource {resource.relative_path}"
                )
            continue
        resources.append(resource)
        known[resource.relative_path] = resource
    guarded = plan_dsh_install(
        install.layout,
        skills=install.skills,
        agents=install.agents,
        rules=install.rules,
        resources=resources,
        permissions=install.permissions,
        instructions=install.instructions,
    )
    output = hooks.output(strict=strict)
    if any(item.path == output.path for item in install.outputs):
        raise ConfigError(
            "DSH hook output is already attached; combine all sources once"
        )
    cached = {item.path: item for item in hooks.resource_outputs}
    for existing_output in install.outputs:
        fresh = cached.get(existing_output.path)
        if fresh is not None and (
            existing_output.source != fresh.source
            or existing_output.source_inventory != fresh.source_inventory
            or existing_output.mode != fresh.mode
        ):
            raise ConfigError(
                f"DSH hook resource changed between plans: {existing_output.path}"
            )
    keys = {item.path for item in install.outputs}
    return replace(
        install,
        activation_diagnostics=(*install.activation_diagnostics, *hooks.diagnostics),
        resources=tuple(resources),
        outputs=(
            *install.outputs,
            *(
                cached.get(item.path, item)
                for item in guarded.outputs
                if item.path not in keys
            ),
            output,
        ),
    )
