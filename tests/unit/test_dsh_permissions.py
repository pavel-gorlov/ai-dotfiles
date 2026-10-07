"""Exact permission translation without grants or lost source restrictions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from ai_dotfiles.core.dsh_permissions import (
    DSH_PERMISSION_GENERATOR_VERSION,
    DSH_PERMISSION_SCHEMA_VERSION,
    DshPermissionPolicy,
    merge_permission_policies,
    translate_permissions,
)
from ai_dotfiles.core.dsh_render import DshProvenance
from ai_dotfiles.core.manifest import DshPermissionMode

_EXACT_TOOLS = [
    ("Read", ("read", "read_image")),
    ("Write", ("write",)),
    ("Edit", ("edit",)),
    ("Glob", ("glob",)),
    ("Grep", ("grep",)),
    ("Bash", ("bash",)),
    ("WebFetch", ("web_fetch",)),
    ("WebSearch", ("web_search",)),
]


def _provenance(origin: str = "domain:@test") -> DshProvenance:
    return DshProvenance(
        Path("/catalog/test/settings.fragment.json"),
        origin,
        "settings:@test",
        "a" * 64,
    )


def _translate(permissions: object) -> DshPermissionPolicy:
    return translate_permissions(permissions, provenance=_provenance())


@pytest.mark.parametrize(("entry", "native"), _EXACT_TOOLS)
@pytest.mark.parametrize("decision", ["deny", "ask"])
def test_only_proven_whole_tools_translate_with_exact_source_provenance(
    entry: str, native: tuple[str, ...], decision: str
) -> None:
    policy = _translate({decision: [entry]})
    assert getattr(policy, decision) == native
    assert policy.required_tools == native
    assert not policy.blocked and not policy.diagnostics
    assert len(policy.contributions) == 1
    contribution = policy.contributions[0]
    assert contribution.decision == decision
    assert contribution.entry == entry
    assert contribution.native_tools == native
    assert contribution.field == f"permissions.{decision}[0]"
    assert contribution.provenance == _provenance()


@pytest.mark.parametrize(
    "entry",
    [
        "Read()",
        "Read(*)",
        "Read(/etc/passwd)",
        "Read( /etc/passwd )",
        "Write(src/**)",
        "Edit(src/**)",
        "Glob(*)",
        "Grep(secret)",
        "Bash()",
        "Bash(*)",
        "Bash(:*)",
        "Bash(git:*)",
        "Bash(git *)",
        "Bash(git status)",
        "Bash(git status && curl example.com)",
        "Bash(git status | head)",
        "Bash(echo x; rm file)",
        "Bash($(command))",
        "WebFetch(domain:example.com)",
        "WebSearch(query:*)",
        "Task",
        "Agent",
        "mcp__server__tool",
        "mcp__server__*",
        "read",
        "read_image",
        "bash",
        "web_fetch",
        "Unknown",
        "*",
        "Bash*",
        "Bash|Read",
        " Bash ",
        "Bash\nRead",
        "Bash \t(git status)",
    ],
)
@pytest.mark.parametrize("decision", ["deny", "ask"])
def test_constraints_unknown_tools_and_native_spellings_never_become_whole_tools(
    entry: str, decision: str
) -> None:
    policy = _translate({decision: [entry]})
    assert policy.blocked
    assert not policy.contributions
    assert policy.deny == policy.ask == policy.required_tools == ()
    gap = policy.gaps[0]
    assert gap.value == entry
    assert gap.provenance == _provenance()
    assert gap.diagnostic.code == "PERMISSION_UNMAPPED"
    assert gap.diagnostic.origin == "domain:@test"
    assert gap.diagnostic.element == "settings:@test"
    assert gap.diagnostic.field == f"permissions.{decision}[0]"
    assert gap.diagnostic.blocking
    assert "manual native policy review" in gap.diagnostic.reason


@pytest.mark.parametrize(
    "entry", ["Read", "Bash", "Bash(git:*)", "Bash(*)", "mcp__server__*", "*"]
)
def test_allow_entries_only_report_loss_of_grant_and_cannot_open_native_access(
    entry: str,
) -> None:
    policy = _translate({"allow": [entry]})
    assert not policy.blocked
    assert not policy.contributions
    assert policy.deny == policy.ask == policy.required_tools == ()
    assert policy.gaps[0].value == entry
    diagnostic = policy.diagnostics[0]
    assert diagnostic.code == "ALLOW_UNMAPPED" and not diagnostic.blocking
    assert diagnostic.field == "permissions.allow[0]"
    payload = policy.bridge_data()
    assert payload["deny"] == payload["ask"] == payload["requiredTools"] == []
    assert set(payload) == {
        "schemaVersion",
        "generator",
        "deny",
        "ask",
        "requiredTools",
        "blocked",
        "contributions",
        "diagnostics",
    }


@pytest.mark.parametrize("value", [None, True, 42, "Bash", [], ["Bash"]])
def test_explicit_invalid_permissions_object_cannot_silently_become_empty(
    value: object,
) -> None:
    policy = _translate(value)
    assert policy.blocked and not policy.contributions
    assert policy.gaps[0].value == value
    assert policy.diagnostics[0].code == "INVALID_FIELD"
    assert policy.diagnostics[0].field == "permissions"
    assert "requires an object" in policy.diagnostics[0].reason


@pytest.mark.parametrize("decision", ["deny", "ask", "allow"])
@pytest.mark.parametrize("value", [None, False, 42, "Bash", {"tool": "Bash"}])
def test_malformed_source_lists_are_diagnosed_with_original_values(
    value: object, decision: str
) -> None:
    policy = _translate({decision: value})
    assert policy.blocked and not policy.contributions
    assert policy.gaps[0].value == value
    assert policy.diagnostics[0].code == "INVALID_FIELD"
    assert policy.diagnostics[0].field == f"permissions.{decision}"
    assert "requires a list" in policy.diagnostics[0].reason


@pytest.mark.parametrize("decision", ["deny", "ask", "allow"])
@pytest.mark.parametrize("value", [None, False, 42, "", " \t\n", [], {"tool": "Bash"}])
def test_invalid_entries_retain_their_own_index_and_do_not_vanish(
    value: object, decision: str
) -> None:
    policy = _translate({decision: ["Read", value, "Bash"]})
    assert policy.blocked
    assert len(policy.gaps) == (3 if decision == "allow" else 1)
    invalid = next(gap for gap in policy.gaps if gap.diagnostic.code == "INVALID_FIELD")
    assert invalid.value == value
    assert invalid.diagnostic.field == f"permissions.{decision}[1]"
    if decision in {"deny", "ask"}:
        assert getattr(policy, decision) == ("bash", "read", "read_image")
        assert [item.field for item in policy.contributions] == [
            f"permissions.{decision}[0]",
            f"permissions.{decision}[2]",
        ]
    else:
        assert not policy.contributions and not policy.required_tools


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("defaultMode", "bypassPermissions"),
        ("defaultMode", "deny"),
        ("disableBypassPermissionsMode", "disable"),
        ("additionalDirectories", ["../outside"]),
        ("unknown", {"restriction": ["secret"]}),
    ],
)
def test_unknown_permission_fields_cannot_select_a_preset_or_drop_restrictions(
    field: str, value: object
) -> None:
    policy = _translate({field: value})
    assert policy.blocked and not policy.contributions
    assert policy.gaps[0].value == value
    assert policy.diagnostics[0].code == "FIELD_UNMAPPED"
    assert policy.diagnostics[0].field == f"permissions[{field!r}]"
    assert "inferring a DSH preset" in policy.diagnostics[0].reason


@pytest.mark.parametrize("mode", ["strict", "native"])
@pytest.mark.parametrize(
    "value",
    [
        "auto",
        "default",
        "acceptEdits",
        "bypassPermissions",
        "dontAsk",
        "plan",
        "Auto",
        None,
        True,
        1,
        [],
        {},
    ],
)
def test_native_acknowledges_only_exact_auto_and_never_grants(
    mode: str, value: object
) -> None:
    provenance = _provenance()
    raw = {"defaultMode": value, "deny": ["Write"], "ask": ["Bash"]}
    policy = translate_permissions(
        raw, provenance=provenance, mode=cast(DshPermissionMode, mode)
    )
    assert policy.blocked is not (mode == "native" and value == "auto")
    assert policy.deny == ("write",) and policy.ask == ("bash",)
    assert policy.gaps[0].value == value
    assert policy.gaps[0].provenance == provenance
    assert policy.gaps[0].diagnostic.blocking == policy.blocked
    assert raw == {"defaultMode": value, "deny": ["Write"], "ask": ["Bash"]}


@pytest.mark.parametrize(
    "restriction",
    [
        {"deny": ["Bash(git:*)"]},
        {"ask": ["Unknown"]},
        {"deny": None},
        {"unknown": True},
        {"allow": [False]},
    ],
)
def test_native_auto_acknowledgement_never_waives_other_permission_gaps(
    restriction: dict[str, object],
) -> None:
    policy = translate_permissions(
        {"defaultMode": "auto", **restriction}, provenance=_provenance(), mode="native"
    )
    assert policy.blocked
    auto = next(gap for gap in policy.gaps if gap.value == "auto")
    assert not auto.diagnostic.blocking
    assert any(item.blocking for item in policy.diagnostics)


def test_names_deduplicate_but_every_source_entry_and_origin_survives_merge() -> None:
    permissions = {
        "deny": ["Read", "Bash", "Read", "Unknown", "Unknown"],
        "ask": ["Bash", "Read"],
        "allow": ["Write"],
    }
    origins = ("global:@test", "project:@test", "local:settings.local.json")
    policies = [
        translate_permissions(permissions, provenance=_provenance(origin))
        for origin in origins
    ]
    merged = merge_permission_policies(iter(policies))
    assert merged.deny == merged.ask == ("bash", "read", "read_image")
    assert merged.required_tools == ("bash", "read", "read_image")
    assert merged.blocked
    assert len(merged.contributions) == 15 and len(merged.gaps) == 9
    assert [item.provenance.origin for item in merged.contributions] == [
        origin for origin in origins for _ in range(5)
    ]
    assert [gap.diagnostic.field for gap in merged.gaps] == [
        field
        for _ in origins
        for field in (
            "permissions.deny[3]",
            "permissions.deny[4]",
            "permissions.allow[0]",
        )
    ]
    assert [gap.diagnostic.origin for gap in merged.gaps] == [
        origin for origin in origins for _ in range(3)
    ]


def test_deny_is_retained_when_same_tool_is_asked_for_or_allowed_elsewhere() -> None:
    merged = merge_permission_policies(
        [
            _translate({"deny": ["Bash"]}),
            _translate({"ask": ["Bash"], "allow": ["Bash"]}),
        ]
    )
    assert merged.deny == merged.ask == merged.required_tools == ("bash",)
    assert not merged.blocked
    assert merged.diagnostics[0].code == "ALLOW_UNMAPPED"


def test_native_names_have_deterministic_order_independent_of_source_order() -> None:
    first = _translate({"deny": ["WebSearch", "Read", "Bash", "Edit", "Read"]})
    second = _translate({"deny": ["Edit", "Bash", "Read", "WebSearch"]})
    assert (
        first.deny
        == second.deny
        == (
            "bash",
            "edit",
            "read",
            "read_image",
            "web_search",
        )
    )
    assert len(first.contributions) == 5 and len(second.contributions) == 4


def test_source_policy_is_unchanged_and_gaps_snapshot_nested_raw_values() -> None:
    args = ["specific"]
    source = {
        "deny": ["Read", {"tool": "Bash", "args": args}],
        "allow": ["Write"],
        "unknown": {"restriction": ["value"]},
    }
    original = copy.deepcopy(source)
    policy = _translate(source)
    payload = policy.bridge_data()
    assert source == original
    assert json.loads(json.dumps(payload)) == payload
    args.append("later")
    assert policy.gaps[0].value == {"tool": "Bash", "args": ["specific"]}
    raw = payload["diagnostics"]
    assert isinstance(raw, list)
    raw[0]["value"]["args"].append("payload mutation")
    assert policy.gaps[0].value == {"tool": "Bash", "args": ["specific"]}
    assert policy.bridge_data()["diagnostics"] != raw


def test_read_only_source_mapping_preserves_constraints() -> None:
    raw = MappingProxyType({"constraint": ["exact"]})
    source = MappingProxyType({"deny": ["Bash", raw], "ask": ["Read"]})
    policy = _translate(source)
    assert policy.blocked
    assert policy.deny == ("bash",) and policy.ask == ("read", "read_image")
    assert policy.gaps[0].value == {"constraint": ["exact"]}
    assert source["deny"][1] is raw
    json.dumps(policy.bridge_data())


def test_bridge_data_exposes_gate_audit_requirements_and_per_entry_provenance() -> None:
    policy = _translate({"deny": ["Read"], "ask": ["Bash"], "allow": ["Write"]})
    payload = policy.bridge_data()
    assert payload == {
        "schemaVersion": DSH_PERMISSION_SCHEMA_VERSION,
        "generator": DSH_PERMISSION_GENERATOR_VERSION,
        "deny": ["read", "read_image"],
        "ask": ["bash"],
        "requiredTools": ["bash", "read", "read_image"],
        "blocked": False,
        "contributions": [item.as_dict() for item in policy.contributions],
        "diagnostics": [gap.as_dict() for gap in policy.gaps],
    }
    assert json.loads(json.dumps(payload)) == payload
    assert all(
        item["provenance"] == _provenance().as_dict()
        for item in payload["contributions"]
    )


def test_empty_sources_and_empty_merge_produce_no_policy_or_preset() -> None:
    empty = DshPermissionPolicy()
    assert _translate({}) == _translate({"deny": [], "ask": [], "allow": []}) == empty
    assert merge_permission_policies([]) == empty
    assert not empty.blocked and not empty.required_tools
