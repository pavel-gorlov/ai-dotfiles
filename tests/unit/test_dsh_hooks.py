"""Pure original-hook contracts; all filesystem and installer I/O is mocked.

Actual published plugin behavior belongs to the isolated native runtime gate,
not an invented Python implementation of its hook protocol.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from ai_dotfiles.core.dsh_config import DshConfigSource
from ai_dotfiles.core.dsh_hooks import (
    DSH_HOOKS_GENERATOR_VERSION,
    DSH_HOOKS_PACKAGE,
    DSH_HOOKS_ROW_ID,
    SUPPORTED_EVENTS,
    DshHookSource,
    attach_dsh_hook_outputs,
    collect_dsh_hooks,
)
from ai_dotfiles.core.dsh_install import DshInstallPlan, DshOutput
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_permissions import DshPermissionPolicy
from ai_dotfiles.core.errors import ConfigError

LAYOUT = project_layout(Path("/project"))


@pytest.fixture
def files(monkeypatch: pytest.MonkeyPatch) -> dict[Path, bytes]:
    data: dict[Path, bytes] = {}

    def read(path: Path) -> bytes:
        if path not in data:
            raise FileNotFoundError(path)
        return data[path]

    def installer(layout: DshLayout, **kwargs: object) -> DshInstallPlan:
        resources = tuple(kwargs.get("resources", ()))
        outputs = []
        for resource in resources:
            inventory = {
                str(path.relative_to(resource.source)): {
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "kind": "file",
                    "mode": 0o755 if path.suffix == ".sh" else 0o644,
                }
                for path, body in data.items()
                if path == resource.source or path.is_relative_to(resource.source)
            }
            outputs.append(
                DshOutput(
                    layout.resources_dir / resource.relative_path,
                    resource.mode,
                    (resource.provenance,),
                    {"resource": resource.provenance.generator},
                    source=resource.source,
                    source_inventory=inventory,
                )
            )
        return DshInstallPlan(
            layout,
            tuple(kwargs.get("skills", ())),
            tuple(kwargs.get("agents", ())),
            tuple(kwargs.get("rules", ())),
            resources,
            tuple(outputs),
            kwargs.get("permissions", DshPermissionPolicy()),
            kwargs.get("instructions"),
        )

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "is_file", lambda path: path in data)
    monkeypatch.setattr("ai_dotfiles.core.dsh_hooks.plan_dsh_install", installer)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=AssertionError("No subprocess in pure unit tests")),
    )
    return data


def source(
    files: dict[Path, bytes],
    hooks: object,
    *,
    name: str = "one",
    scope: str = "project",
    bare: bool = False,
    required: tuple[str, ...] = (),
) -> DshHookSource:
    path = (
        Path("/origins")
        / scope
        / name
        / ("hooks.json" if bare else "settings.fragment.json")
    )
    files[path] = json.dumps(hooks if bare else {"hooks": hooks}).encode()
    return DshHookSource(
        path, scope, "@" + name, "@" + name, required_semantics=required
    )


def group(command: str = "true", **handler: object) -> list[dict[str, object]]:
    return [{"hooks": [{"type": "command", "command": command, **handler}]}]


def empty_install(layout: DshLayout = LAYOUT) -> DshInstallPlan:
    return DshInstallPlan(layout, (), (), (), (), (), DshPermissionPolicy(), None)


def test_all_events_and_multiple_domains_scopes_combine_once_without_dedup(
    files: dict[Path, bytes],
) -> None:
    project = source(
        files,
        {event: group("echo project") for event in SUPPORTED_EVENTS},
        name="project",
    )
    global_one = source(
        files,
        {event: group("echo global") for event in SUPPORTED_EVENTS},
        scope="global",
    )
    global_two = source(
        files,
        {event: group("echo global") for event in SUPPORTED_EVENTS},
        scope="global",
        name="two",
    )
    plan = collect_dsh_hooks([project, global_one, global_two], LAYOUT)
    assert not plan.blocked
    assert list(plan.hooks) == list(SUPPORTED_EVENTS)
    for event in SUPPORTED_EVENTS:
        assert [entry["hooks"][0]["command"] for entry in plan.hooks[event]] == [
            "echo global",
            "echo global",
            "echo project",
        ]
    contribution = plan.contribution()
    assert contribution is not None
    assert contribution.name == "hooks"
    assert contribution.scope == "project"
    assert len(contribution.rows) == 1
    assert contribution.rows[0] == {
        "id": DSH_HOOKS_ROW_ID,
        "name": DSH_HOOKS_PACKAGE,
        "config": {"configPath": str(LAYOUT.hooks_path), "projectDir": "/project"},
    }
    assert contribution.requirements.required_ids == (DSH_HOOKS_ROW_ID,)
    assert contribution.requirements.required_services == (
        "shell",
        "sessionProjections",
    )
    assert [part.source for part in contribution.provenance] == [
        global_one.path,
        global_two.path,
        project.path,
    ]
    output = plan.output()
    assert output.path == LAYOUT.hooks_path
    assert output.mode == "generated"
    assert output.generators == {"hooks": DSH_HOOKS_GENERATOR_VERSION}
    raw = json.loads(output.content)
    assert raw["hooks"] == plan.hooks
    assert raw["aiDotfiles"]["sources"][0]["value"] == json.loads(
        files[global_one.path]
    )
    assert {record["status"] for record in plan.sources} == {"READY"}


@pytest.mark.parametrize(
    ("matcher", "mapped"),
    [
        ("Read", "read|read_image"),
        (
            "Write|Edit|Glob|Grep|Bash|WebFetch|WebSearch",
            "write|edit|glob|grep|bash|web_fetch|web_search",
        ),
        ("Bash|Read|Bash", "bash|read|read_image"),
        ("", ""),
        ("*", "*"),
    ],
)
@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse"])
def test_known_tool_matchers_map_exactly(
    files: dict[Path, bytes], matcher: str, mapped: str, event: str
) -> None:
    groups = group()
    groups[0]["matcher"] = matcher
    plan = collect_dsh_hooks([source(files, {event: groups})], LAYOUT)
    assert not plan.blocked
    assert plan.hooks[event][0]["matcher"] == mapped


@pytest.mark.parametrize(
    "matcher",
    [
        "Agent",
        "Task",
        "mcp__server__tool",
        "bash",
        "Bash|Unknown",
        "^Bash$",
        "B.*",
        "(",
        4,
        [],
        {},
        None,
    ],
)
def test_unmapped_matcher_never_widens(
    files: dict[Path, bytes], matcher: object
) -> None:
    groups = group("exit 2")
    groups[0]["matcher"] = matcher
    plan = collect_dsh_hooks([source(files, {"PreToolUse": groups})], LAYOUT)
    assert plan.blocked
    assert not plan.hooks
    assert any(
        item.field.endswith(".matcher") and item.blocking for item in plan.diagnostics
    )
    assert plan.sources[0]["status"] == "MANUAL"
    with pytest.raises(ConfigError, match="MANUAL"):
        plan.contribution()


@pytest.mark.parametrize(
    ("event", "matcher", "valid"),
    [
        ("SessionStart", "startup|resume", True),
        ("SessionStart", "new", False),
        ("SubagentStart", "general-purpose", True),
        ("SubagentStop", "general-purpose", True),
        ("SubagentStart", "reviewer", False),
        ("SubagentStop", "general-purpose|reviewer", False),
        ("Stop", "something", False),
        ("UserPromptSubmit", "something", False),
    ],
)
def test_exact_non_tool_subjects_and_ignored_matchers_are_reported(
    files: dict[Path, bytes], event: str, matcher: str, valid: bool
) -> None:
    groups = group()
    groups[0]["matcher"] = matcher
    plan = collect_dsh_hooks([source(files, {event: groups})], LAYOUT)
    assert plan.blocked is not valid
    if valid:
        assert plan.hooks[event][0]["matcher"].startswith("^(?:")


@pytest.mark.parametrize(
    "event",
    [
        "Setup",
        "InstructionsLoaded",
        "UserPromptExpansion",
        "MessageDisplay",
        "PermissionRequest",
        "PostToolUseFailure",
        "PostToolBatch",
        "PermissionDenied",
        "Notification",
        "TaskCreated",
        "TaskCompleted",
        "StopFailure",
        "TeammateIdle",
        "ConfigChange",
        "CwdChanged",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreCompact",
        "PostCompact",
        "SessionEnd",
        "Elicitation",
        "ElicitationResult",
        "FutureEvent",
    ],
)
def test_every_unsupported_event_is_detected_before_native_parse(
    files: dict[Path, bytes], event: str
) -> None:
    plan = collect_dsh_hooks([source(files, {event: group()})], LAYOUT)
    assert plan.blocked
    assert not plan.hooks
    assert plan.diagnostics[0].field == "hooks." + event
    assert plan.sources[0]["value"]["hooks"][event] == group()


@pytest.mark.parametrize(
    "handler_type", ["http", "mcp_tool", "prompt", "agent", None, 7]
)
def test_non_command_types_are_manual(
    files: dict[Path, bytes], handler_type: object
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {"Stop": group(type=handler_type)})], LAYOUT
    )
    assert plan.blocked
    assert not plan.hooks
    assert plan.diagnostics[0].field.endswith(".type")


@pytest.mark.parametrize(
    "field",
    [
        "args",
        "async",
        "asyncRewake",
        "shell",
        "if",
        "once",
        "statusMessage",
        "updatedInput",
        "systemMessage",
        "continue",
        "futureOption",
    ],
)
@pytest.mark.parametrize("value", [True, False])
def test_every_ignored_handler_option_is_not_silently_removed(
    files: dict[Path, bytes], field: str, value: object
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {"PreToolUse": group(**{field: value})})], LAYOUT
    )
    assert plan.blocked
    assert not plan.hooks
    assert any(
        item.field.endswith("." + field) and item.blocking for item in plan.diagnostics
    )
    with pytest.raises(ConfigError):
        plan.output()


@pytest.mark.parametrize("bad", [None, "group", 1, {}])
def test_malformed_event_groups_are_diagnosed(
    files: dict[Path, bytes], bad: object
) -> None:
    plan = collect_dsh_hooks([source(files, {"Stop": bad})], LAYOUT)
    assert plan.blocked


@pytest.mark.parametrize(
    "groups",
    [
        [None],
        [{}],
        [{"hooks": None}],
        [{"hooks": [None]}],
        [{"once": True, "hooks": [{"command": "true"}]}],
    ],
)
def test_malformed_or_ignored_group_fields_are_diagnosed(
    files: dict[Path, bytes], groups: object
) -> None:
    assert collect_dsh_hooks([source(files, {"Stop": groups})], LAYOUT).blocked


@pytest.mark.parametrize("command", [None, "", "   ", 42, {}])
def test_missing_non_string_or_empty_command_is_manual(
    files: dict[Path, bytes], command: object
) -> None:
    assert collect_dsh_hooks([source(files, {"Stop": group(command)})], LAYOUT).blocked


@pytest.mark.parametrize("timeout", [True, False, 0, -1, "30", None])
def test_invalid_timeout_cannot_reach_native(
    files: dict[Path, bytes], timeout: object
) -> None:
    assert collect_dsh_hooks(
        [source(files, {"Stop": group(timeout=timeout)})], LAYOUT
    ).blocked


def test_positive_timeout_and_omitted_type_are_preserved(
    files: dict[Path, bytes],
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {"Stop": [{"hooks": [{"command": "true", "timeout": 0.5}]}]})],
        LAYOUT,
    )
    assert plan.hooks["Stop"][0]["hooks"] == [
        {"type": "command", "command": "true", "timeout": 0.5}
    ]


@pytest.mark.parametrize(
    ("event", "semantics"),
    [
        ("Stop", ("exit-2", "Stop.block")),
        ("PreToolUse", ("exit-2", "permissionDecision.deny", "permissionDecision.ask")),
        ("UserPromptSubmit", ("exit-2", "additionalContext")),
        ("PostToolUse", ("exit-2", "additionalContext")),
        ("SessionStart", ("additionalContext",)),
        ("SubagentStart", ("additionalContext",)),
    ],
)
def test_supported_native_protocol_requirements_remain_ready(
    files: dict[Path, bytes], event: str, semantics: tuple[str, ...]
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {event: group()}, required=semantics)], LAYOUT
    )
    assert not plan.blocked
    assert plan.contribution() is not None


@pytest.mark.parametrize(
    ("event", "semantic"),
    [
        ("PreToolUse", "updatedInput"),
        ("PreToolUse", "additionalContext"),
        ("PreToolUse", "permissionDecision.allow"),
        ("PreToolUse", "permissionDecision.defer"),
        ("PostToolUse", "updatedToolOutput"),
        ("PostToolUse", "updatedMCPToolOutput"),
        ("PostToolUse", "tool_response"),
        ("Stop", "stop_hook_active"),
        ("Stop", "continue:false"),
        ("Stop", "systemMessage"),
        ("Stop", "transcript_path"),
        ("Stop", "suppressOutput"),
        ("Stop", "stopReason"),
        ("Stop", "terminalSequence"),
        ("SubagentStop", "exit-2"),
        ("SubagentStop", "additionalContext"),
        ("SubagentStart", "agent_type"),
        ("SubagentStart", "session_id"),
        ("SessionStart", "stdout"),
        ("SessionStart", "initialUserMessage"),
        ("SessionStart", "sessionTitle"),
        ("SessionStart", "watchPaths"),
        ("SessionStart", "reloadSkills"),
        ("SessionStart", "CLAUDE_ENV_FILE"),
        ("UserPromptSubmit", "suppressOriginalPrompt"),
        ("Stop", "unknownProtocol"),
    ],
)
def test_required_incompatible_behavior_is_manual(
    files: dict[Path, bytes], event: str, semantic: str
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {event: group()}, required=(semantic,))], LAYOUT
    )
    assert plan.blocked
    assert not plan.hooks
    assert any(
        item.field.endswith(".required." + semantic) for item in plan.diagnostics
    )
    assert plan.sources[0]["requiredSemantics"] == [semantic]


def test_each_handler_carries_bounded_payload_and_output_diagnostics(
    files: dict[Path, bytes],
) -> None:
    plan = collect_dsh_hooks(
        [source(files, {event: group() for event in SUPPORTED_EVENTS})], LAYOUT
    )
    for event in SUPPORTED_EVENTS:
        fields = {
            item.field
            for item in plan.diagnostics
            if item.field.startswith("hooks." + event + "[")
        }
        for field in (
            "transcript_path",
            "systemMessage",
            "continue:false",
            "execution",
        ):
            assert any(item.endswith(".native." + field) for item in fields)
    assert any("flattened text" in item.reason for item in plan.diagnostics)
    assert any("constant general-purpose" in item.reason for item in plan.diagnostics)
    assert any("no consecutive-block cap" in item.reason for item in plan.diagnostics)
    assert not any(item.blocking for item in plan.diagnostics)


@pytest.mark.parametrize(
    "prefix",
    [
        "${CLAUDE_PLUGIN_ROOT}/hooks/",
        "$CLAUDE_PLUGIN_ROOT/hooks/",
        "$CLAUDE_PROJECT_DIR/.claude/hooks/",
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/",
        ".claude/hooks/",
        "./.claude/hooks/",
        "hooks/",
        "./hooks/",
    ],
)
@pytest.mark.parametrize("interpreter", ["", "bash ", "/bin/sh ", "python3 ", "node "])
def test_only_known_launch_resource_is_bound_and_literal_arguments_are_exact(
    files: dict[Path, bytes], prefix: str, interpreter: str
) -> None:
    original = (
        interpreter + '"' + prefix + 'run.sh" --literal "./unchanged {{ value }}"'
    )
    item = source(files, {"Stop": group(original)})
    item = replace(item, source_root=item.path.parent)
    files[item.path.parent / "hooks/run.sh"] = (
        b'#!/bin/sh\nprintf "%s" "{{ untouched }}"\n'
    )
    files[item.path.parent / "support/data.json"] = b'{"path":"./keep-me"}'
    before = dict(files)
    plan = collect_dsh_hooks([item], LAYOUT)
    assert not plan.blocked
    root = Path(plan.sources[0]["bindingRoot"])
    assert (
        plan.hooks["Stop"][0]["hooks"][0]["command"]
        == interpreter
        + str(root / "hooks/run.sh")
        + ' --literal "./unchanged {{ value }}"'
    )
    assert files == before
    assert any(resource.source == item.path.parent for resource in plan.resources)
    copied = next(
        output for output in plan.resource_outputs if output.source == item.path.parent
    )
    assert "support/data.json" in copied.source_inventory
    assert copied.source_inventory["hooks/run.sh"]["mode"] == 0o755


@pytest.mark.parametrize(
    "command",
    [
        "$CLAUDE_PROJECT_DIR/.claude/hooks/missing.sh",
        "${CLAUDE_PLUGIN_ROOT}/../outside.sh",
        'echo "${CLAUDE_PLUGIN_ROOT}/literal"',
        "true; $CLAUDE_PROJECT_DIR/.claude/hooks/run.sh",
    ],
)
def test_unavailable_traversing_or_complex_unbound_resource_is_manual(
    files: dict[Path, bytes], command: str
) -> None:
    assert collect_dsh_hooks([source(files, {"Stop": group(command)})], LAYOUT).blocked


def test_config_domain_binding_reused_and_cross_scope_origin_copied(
    files: dict[Path, bytes],
) -> None:
    domain = source(files, {"Stop": group()}, name="domain")
    original = DshConfigSource(
        domain.path,
        "settings",
        "project",
        "@domain",
        "@domain",
        LAYOUT.resources_dir / "domains/domain",
    )
    global_domain = replace(
        original,
        scope="global",
        binding_root=Path("/dsh-home/ai-dotfiles/resources/domains/domain"),
    )
    plan = collect_dsh_hooks([original, global_domain], LAYOUT)
    assert Path(plan.sources[1]["bindingRoot"]) == original.binding_root
    assert Path(plan.sources[0]["bindingRoot"]).is_relative_to(
        LAYOUT.resources_dir / "hook-origins"
    )
    assert len(plan.hooks["Stop"]) == 2
    assert all(resource.mode == "copy" for resource in plan.resources)


def test_local_bare_original_copy_and_source_provenance_are_retained(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {"Stop": group()}, bare=True)
    plan = collect_dsh_hooks([item], LAYOUT)
    assert plan.hooks["Stop"] == group()
    assert (
        plan.provenance[0].source_sha256 == hashlib.sha256(files[item.path]).hexdigest()
    )
    assert any(
        resource.source == item.path
        and resource.relative_path.parts[0] == "hook-sources"
        for resource in plan.resources
    )


def test_global_plan_defers_project_binding_to_session_and_launcher_can_bind(
    files: dict[Path, bytes],
) -> None:
    layout = global_layout("/dsh-home")
    item = source(files, {"Stop": group()}, scope="global")
    plan = collect_dsh_hooks([item], layout)
    assert plan.contribution().scope == "global"
    assert "projectDir" not in plan.contribution().rows[0]["config"]
    launched = collect_dsh_hooks([item], layout, project_root=Path("/launched-project"))
    assert (
        launched.contribution().rows[0]["config"]["projectDir"] == "/launched-project"
    )


def test_no_hooks_settings_and_other_source_kinds_produce_no_native_row(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {})
    files[item.path] = b'{"env":{"KEY":"literal"}}'
    ignored = DshConfigSource(
        Path("/unread/mcp.json"), "mcp", "project", "local", "mcp", Path("/")
    )
    plan = collect_dsh_hooks([item, ignored], LAYOUT)
    assert plan.contribution() is None
    assert len(plan.sources) == 1


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b'{"hooks":NaN}', b"\xff"])
def test_invalid_source_json_never_reaches_native(
    files: dict[Path, bytes], raw: bytes
) -> None:
    item = source(files, {})
    files[item.path] = raw
    with pytest.raises(ConfigError):
        collect_dsh_hooks([item], LAYOUT)


@pytest.mark.parametrize("change", ["modified", "removed"])
def test_attach_refuses_source_change_before_inventory_refresh(
    files: dict[Path, bytes], change: str
) -> None:
    item = source(files, {"Stop": group()})
    plan = collect_dsh_hooks([item], LAYOUT)
    if change == "modified":
        files[item.path] = b'{"hooks":{}}'
    else:
        del files[item.path]
    with pytest.raises(ConfigError, match="source"):
        attach_dsh_hook_outputs(empty_install(), plan)


def test_attach_preserves_complete_existing_plan_and_cached_resource_snapshot(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {"Stop": group("bash hooks/run.sh")})
    files[item.path.parent / "hooks/run.sh"] = b"#!/bin/sh\ntrue\n"
    support = item.path.parent / "hooks/support.txt"
    files[support] = b"initial"
    plan = collect_dsh_hooks([item], LAYOUT)
    previous = DshOutput(
        LAYOUT.bridge_path, "generated", (), {"bridge": 1}, content=b"existing bridge"
    )
    install = replace(empty_install(), outputs=(previous,), instructions=Mock())
    files[support] = b"changed after hook planning"
    attached = attach_dsh_hook_outputs(install, plan)
    assert attached.outputs[0] is previous
    assert attached.instructions is install.instructions
    assert attached.permissions is install.permissions
    assert attached.skills == install.skills
    assert attached.agents == install.agents
    assert attached.rules == install.rules
    assert attached.outputs[-1].path == LAYOUT.hooks_path
    origin = next(
        output
        for output in attached.outputs
        if output.source == item.path.parent / "hooks"
    )
    assert (
        origin.source_inventory["support.txt"]["sha256"]
        == hashlib.sha256(b"initial").hexdigest()
    )
    with pytest.raises(ConfigError, match="already attached"):
        attach_dsh_hook_outputs(attached, plan)


def test_existing_domain_resource_is_not_duplicated_and_inventory_conflict_refuses(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {"Stop": group()})
    plan = collect_dsh_hooks([item], LAYOUT)
    resource = plan.resources[0]
    output = plan.resource_outputs[0]
    install = replace(empty_install(), resources=(resource,), outputs=(output,))
    attached = attach_dsh_hook_outputs(install, plan)
    assert attached.resources.count(resource) == 1
    assert attached.outputs.count(output) == 1
    with pytest.raises(ConfigError, match="between plans"):
        attach_dsh_hook_outputs(
            replace(install, outputs=(replace(output, source_inventory={}),)), plan
        )
    with pytest.raises(ConfigError, match="Conflicting"):
        attach_dsh_hook_outputs(
            replace(install, resources=(replace(resource, source=Path("/other")),)),
            plan,
        )


def test_unsafe_origin_binding_and_destination_recursion_refuse(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {"Stop": group()})
    for changed in (
        replace(item, binding_root=Path("/outside")),
        replace(item, source_root=Path("/other")),
    ):
        with pytest.raises(ConfigError):
            collect_dsh_hooks([changed], LAYOUT)
    root_source = Path("/project/hooks.json")
    files[root_source] = b"{}"
    with pytest.raises(ConfigError, match="contains its destination"):
        collect_dsh_hooks(
            [
                DshHookSource(
                    root_source,
                    "project",
                    "local",
                    "hooks",
                    source_root=root_source.parent,
                )
            ],
            LAYOUT,
        )


def test_shared_resource_binding_between_different_origins_refuses(
    files: dict[Path, bytes],
) -> None:
    one = source(files, {"Stop": group("bash hooks/run.sh")})
    two = source(files, {"Stop": group("bash hooks/run.sh")}, name="two")
    files[one.path.parent / "hooks/run.sh"] = b"true"
    files[two.path.parent / "hooks/run.sh"] = b"true"
    binding = LAYOUT.resources_dir / "domains/shared"
    with pytest.raises(ConfigError, match="share resource binding"):
        collect_dsh_hooks(
            [replace(one, binding_root=binding), replace(two, binding_root=binding)],
            LAYOUT,
        )


def test_hooks_map_and_required_semantics_retain_origin_even_when_manual(
    files: dict[Path, bytes],
) -> None:
    item = source(files, None)
    plan = collect_dsh_hooks([item], LAYOUT)
    assert plan.blocked
    assert plan.diagnostics[0].origin == "@one"
    assert plan.diagnostics[0].element == "@one"


def test_attach_layout_mismatch_refuses(files: dict[Path, bytes]) -> None:
    plan = collect_dsh_hooks([source(files, {"Stop": group()})], LAYOUT)
    with pytest.raises(ConfigError, match="layouts differ"):
        attach_dsh_hook_outputs(empty_install(global_layout("/dsh-home")), plan)


@pytest.mark.parametrize("has_handler", [False, True])
@pytest.mark.parametrize("scope", ["global", "project"])
def test_implicit_local_origin_never_inventories_unrelated_parent_state(
    files: dict[Path, bytes], has_handler: bool, scope: str
) -> None:
    item = source(
        files, {"Stop": group("bash hooks/run.sh")} if has_handler else {}, scope=scope
    )
    files[item.path.parent / "hooks/run.sh"] = b"true"
    files[item.path.parent / "hooks/data/support.txt"] = b"needed support"
    files[item.path.parent / "projects/private-history.jsonl"] = (
        b"unrelated private state"
    )
    files[item.path.parent / "unrelated.txt"] = b"not a hook resource"
    plan = collect_dsh_hooks([item], LAYOUT)
    assert all(resource.source != item.path.parent for resource in plan.resources)
    assert all(
        not any(
            "private-history" in name or "unrelated" in name
            for name in output.source_inventory
        )
        for output in plan.resource_outputs
    )
    if has_handler:
        copied = next(
            output
            for output in plan.resource_outputs
            if output.source == item.path.parent / "hooks"
        )
        assert "data/support.txt" in copied.source_inventory
    else:
        assert [resource.source for resource in plan.resources] == [item.path]
        assert plan.contribution() is None


def test_implicit_plugin_support_outside_hooks_requires_explicit_bounded_root(
    files: dict[Path, bytes],
) -> None:
    item = source(files, {"Stop": group("${CLAUDE_PLUGIN_ROOT}/scripts/run.sh")})
    files[item.path.parent / "scripts/run.sh"] = b"true"
    assert collect_dsh_hooks([item], LAYOUT).blocked
    plan = collect_dsh_hooks([replace(item, source_root=item.path.parent)], LAYOUT)
    assert not plan.blocked
    assert any(resource.source == item.path.parent for resource in plan.resources)


@pytest.mark.parametrize(
    "prefix", ["${HOME}/.claude/hooks/", "$HOME/.claude/hooks/", "~/.claude/hooks/"]
)
def test_global_home_handler_reference_is_origin_bound_without_real_home(
    files: dict[Path, bytes], prefix: str
) -> None:
    item = source(files, {"Stop": group(prefix + "run.sh")}, scope="global")
    files[item.path.parent / "hooks/run.sh"] = b"true"
    plan = collect_dsh_hooks([item], LAYOUT)
    assert not plan.blocked
    assert (
        str(Path(plan.sources[0]["bindingRoot"]) / "hooks/run.sh")
        == plan.hooks["Stop"][0]["hooks"][0]["command"]
    )
    project = replace(item, scope="project")
    assert collect_dsh_hooks([project], LAYOUT).blocked
