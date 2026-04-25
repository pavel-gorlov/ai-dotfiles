"""Unit tests for ai_dotfiles.core.settings_merge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.settings_merge import (
    assemble_settings,
    collect_domain_fragments,
    collect_fragment_contributions,
    deep_merge_hooks,
    deep_merge_settings,
    hook_signature,
    load_fragment,
    strip_meta,
    strip_owned,
    write_settings,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_fragment_existing(tmp_path: Path) -> None:
    fragment = {"hooks": {"PostToolUse": []}}
    path = tmp_path / "settings.fragment.json"
    _write_json(path, fragment)
    assert load_fragment(path) == fragment


def test_load_fragment_missing(tmp_path: Path) -> None:
    assert load_fragment(tmp_path / "nope.json") == {}


def test_load_fragment_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_fragment(path)


def test_load_fragment_not_object(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_fragment(path)


def test_strip_meta_returns_copy() -> None:
    # `strip_meta` is a no-op now (meta lives in domain.json), but it
    # still returns a defensive copy so callers can mutate freely.
    fragment = {"hooks": {"PostToolUse": []}, "env": {"FOO": "bar"}}
    result = strip_meta(fragment)
    assert result == fragment
    assert result is not fragment


def test_strip_meta_empty() -> None:
    assert strip_meta({}) == {}


def test_deep_merge_hooks_disjoint_events() -> None:
    base = {"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"cmd": "a"}]}]}}
    overlay = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"cmd": "b"}]}]}}
    result = deep_merge_hooks(base, overlay)
    assert set(result["hooks"].keys()) == {"PostToolUse", "PreToolUse"}
    assert result["hooks"]["PostToolUse"] == [
        {"matcher": "Edit", "hooks": [{"cmd": "a"}]}
    ]
    assert result["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [{"cmd": "b"}]}
    ]


def test_deep_merge_hooks_same_event() -> None:
    base = {"hooks": {"PostToolUse": [{"cmd": "a"}]}}
    overlay = {"hooks": {"PostToolUse": [{"cmd": "b"}]}}
    result = deep_merge_hooks(base, overlay)
    assert result["hooks"]["PostToolUse"] == [{"cmd": "a"}, {"cmd": "b"}]


def test_deep_merge_hooks_non_hook_keys() -> None:
    base = {"env": {"FOO": "1"}, "model": "sonnet"}
    overlay = {"env": {"BAR": "2"}, "model": "opus"}
    result = deep_merge_hooks(base, overlay)
    # Overlay overwrites top-level non-hook keys.
    assert result["env"] == {"BAR": "2"}
    assert result["model"] == "opus"


def test_deep_merge_hooks_empty_base() -> None:
    overlay = {"hooks": {"PostToolUse": [{"cmd": "a"}]}, "x": 1}
    result = deep_merge_hooks({}, overlay)
    assert result == {"hooks": {"PostToolUse": [{"cmd": "a"}]}, "x": 1}


def test_deep_merge_hooks_empty_overlay() -> None:
    base = {"hooks": {"PostToolUse": [{"cmd": "a"}]}, "x": 1}
    result = deep_merge_hooks(base, {})
    assert result == {"hooks": {"PostToolUse": [{"cmd": "a"}]}, "x": 1}


def test_deep_merge_hooks_does_not_mutate_inputs() -> None:
    base = {"hooks": {"PostToolUse": [{"cmd": "a"}]}}
    overlay = {"hooks": {"PostToolUse": [{"cmd": "b"}]}}
    deep_merge_hooks(base, overlay)
    assert base == {"hooks": {"PostToolUse": [{"cmd": "a"}]}}
    assert overlay == {"hooks": {"PostToolUse": [{"cmd": "b"}]}}


def test_assemble_single_fragment(tmp_path: Path) -> None:
    frag = tmp_path / "python" / "settings.fragment.json"
    _write_json(
        frag,
        {"hooks": {"PostToolUse": [{"cmd": "ruff"}]}},
    )
    result = assemble_settings([frag])
    assert result == {"hooks": {"PostToolUse": [{"cmd": "ruff"}]}}


def test_assemble_multiple_fragments(tmp_path: Path) -> None:
    frag_py = tmp_path / "python" / "settings.fragment.json"
    _write_json(
        frag_py,
        {
            "hooks": {
                "PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"cmd": "ruff"}]}]
            },
        },
    )
    frag_go = tmp_path / "go" / "settings.fragment.json"
    _write_json(
        frag_go,
        {
            "hooks": {
                "PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"cmd": "gofmt"}]}],
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"cmd": "go-vet"}]}],
            },
        },
    )
    # Caller-supplied order is preserved (used by collect_domain_fragments
    # to enforce topological order). go first, python second.
    result = assemble_settings([frag_go, frag_py])

    assert result["hooks"]["PostToolUse"] == [
        {"matcher": "Edit|Write", "hooks": [{"cmd": "gofmt"}]},
        {"matcher": "Edit|Write", "hooks": [{"cmd": "ruff"}]},
    ]
    assert result["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [{"cmd": "go-vet"}]}
    ]

    # Reversing the input reverses the merge order.
    result_rev = assemble_settings([frag_py, frag_go])
    assert result_rev["hooks"]["PostToolUse"] == [
        {"matcher": "Edit|Write", "hooks": [{"cmd": "ruff"}]},
        {"matcher": "Edit|Write", "hooks": [{"cmd": "gofmt"}]},
    ]


def test_assemble_with_base(tmp_path: Path) -> None:
    frag = tmp_path / "python" / "settings.fragment.json"
    _write_json(
        frag,
        {"hooks": {"PostToolUse": [{"cmd": "ruff"}]}},
    )
    base = {
        "env": {"FOO": "1"},
        "hooks": {"PostToolUse": [{"cmd": "base"}]},
    }
    result = assemble_settings([frag], base=base)
    assert result["env"] == {"FOO": "1"}
    assert result["hooks"]["PostToolUse"] == [{"cmd": "base"}, {"cmd": "ruff"}]


def test_assemble_empty_list() -> None:
    assert assemble_settings([]) == {}
    assert assemble_settings([], base={"x": 1}) == {"x": 1}


def test_write_settings(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "settings.json"
    settings = {"hooks": {"PostToolUse": [{"cmd": "a"}]}, "env": {"X": "1"}}
    write_settings(settings, target)
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    loaded = json.loads(text)
    assert loaded == settings
    # indent=2 produces multi-line output.
    assert "\n  " in text


def test_collect_domain_fragments(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    # Create fragments for python and go domains.
    (catalog / "python").mkdir(parents=True)
    (catalog / "python" / "settings.fragment.json").write_text("{}", encoding="utf-8")
    (catalog / "go").mkdir(parents=True)
    (catalog / "go" / "settings.fragment.json").write_text("{}", encoding="utf-8")
    # Domain without a fragment file.
    (catalog / "rust").mkdir(parents=True)

    packages = [
        "@python",
        "@go",
        "@rust",  # no fragment -> skipped
        "skill:code-review",  # standalone -> skipped
        "agent:researcher",  # standalone -> skipped
        "rule:security",  # standalone -> skipped
    ]
    result = collect_domain_fragments(packages, catalog)
    assert set(result) == {
        catalog / "python" / "settings.fragment.json",
        catalog / "go" / "settings.fragment.json",
    }


def test_collect_domain_fragments_empty(tmp_path: Path) -> None:
    assert collect_domain_fragments([], tmp_path) == []


def test_collect_domain_fragments_topological_order(tmp_path: Path) -> None:
    """A manually-edited manifest with the wrong order still yields a
    topologically-sorted fragment list (deps before dependents)."""
    catalog = tmp_path / "catalog"
    (catalog / "base").mkdir(parents=True)
    (catalog / "base" / "domain.json").write_text(
        json.dumps({"name": "base"}), encoding="utf-8"
    )
    (catalog / "base" / "settings.fragment.json").write_text(
        json.dumps({"permissions": {"allow": ["BaseAllow"]}}), encoding="utf-8"
    )
    (catalog / "child").mkdir(parents=True)
    (catalog / "child" / "domain.json").write_text(
        json.dumps({"name": "child", "depends": ["@base"]}), encoding="utf-8"
    )
    (catalog / "child" / "settings.fragment.json").write_text(
        json.dumps({"permissions": {"allow": ["ChildAllow"]}}), encoding="utf-8"
    )

    # Manifest declares child BEFORE base — wrong order.
    fragments = collect_domain_fragments(["@child", "@base"], catalog)
    assert fragments == [
        catalog / "base" / "settings.fragment.json",
        catalog / "child" / "settings.fragment.json",
    ]


# ── deep_merge_settings: permissions concat/dedup ──────────────────────────


def test_deep_merge_settings_concats_permissions_allow() -> None:
    base = {"permissions": {"allow": ["Read", "Write"]}}
    overlay = {"permissions": {"allow": ["Edit"]}}
    result = deep_merge_settings(base, overlay)
    assert result["permissions"]["allow"] == ["Read", "Write", "Edit"]


def test_deep_merge_settings_dedups_permissions_allow() -> None:
    base = {"permissions": {"allow": ["Read", "Write"]}}
    overlay = {"permissions": {"allow": ["Write", "Edit"]}}
    result = deep_merge_settings(base, overlay)
    assert result["permissions"]["allow"] == ["Read", "Write", "Edit"]


def test_deep_merge_settings_preserves_first_seen_order() -> None:
    base = {"permissions": {"allow": ["c", "a"]}}
    overlay = {"permissions": {"allow": ["b", "a"]}}
    result = deep_merge_settings(base, overlay)
    assert result["permissions"]["allow"] == ["c", "a", "b"]


def test_deep_merge_settings_handles_deny_and_ask() -> None:
    base = {"permissions": {"deny": ["X"], "ask": ["P"]}}
    overlay = {"permissions": {"deny": ["Y"], "ask": ["Q"]}}
    result = deep_merge_settings(base, overlay)
    assert result["permissions"]["deny"] == ["X", "Y"]
    assert result["permissions"]["ask"] == ["P", "Q"]


def test_deep_merge_settings_overlay_wins_on_non_list_keys() -> None:
    base = {"model": "haiku", "env": {"X": "1"}}
    overlay = {"model": "opus", "env": {"X": "2"}}
    result = deep_merge_settings(base, overlay)
    assert result["model"] == "opus"
    assert result["env"] == {"X": "2"}


def test_deep_merge_settings_hooks_still_concat_per_event() -> None:
    base = {"hooks": {"PostToolUse": [{"matcher": "A"}]}}
    overlay = {"hooks": {"PostToolUse": [{"matcher": "B"}]}}
    result = deep_merge_settings(base, overlay)
    assert result["hooks"]["PostToolUse"] == [
        {"matcher": "A"},
        {"matcher": "B"},
    ]


def test_deep_merge_hooks_alias_still_works() -> None:
    # Backwards-compat: deep_merge_hooks is an alias for deep_merge_settings.
    assert deep_merge_hooks is deep_merge_settings


def test_assemble_settings_with_base_merges_into_existing(tmp_path: Path) -> None:
    user_base = {
        "permissions": {"allow": ["Read", "Bash(git status)"]},
        "model": "opus",
    }
    fragment = tmp_path / "x.fragment.json"
    _write_json(
        fragment,
        {"permissions": {"allow": ["Bash(git log)"]}},
    )
    result = assemble_settings([fragment], base=user_base)
    assert result["permissions"]["allow"] == [
        "Read",
        "Bash(git status)",
        "Bash(git log)",
    ]
    assert result["model"] == "opus"


# ── hook_signature / collect_fragment_contributions / strip_owned ──────────


def test_hook_signature_is_deterministic_and_stable() -> None:
    a = {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}
    b = {"hooks": [{"command": "x", "type": "command"}], "matcher": "Bash"}
    # Same content, different key order — same signature.
    assert hook_signature(a) == hook_signature(b)
    # Different content -> different signature.
    c = {"matcher": "Edit"}
    assert hook_signature(a) != hook_signature(c)


def test_collect_fragment_contributions_aggregates(tmp_path: Path) -> None:
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    _write_json(
        f1,
        {
            "permissions": {"allow": ["P1"], "deny": ["D1"]},
            "hooks": {"PostToolUse": [{"matcher": "A"}]},
        },
    )
    _write_json(
        f2,
        {
            "permissions": {"allow": ["P2", "P1"]},
            "hooks": {"PostToolUse": [{"matcher": "B"}]},
        },
    )
    contrib = collect_fragment_contributions([f1, f2])
    assert contrib["permissions_allow"] == ["P1", "P2"]
    assert contrib["permissions_deny"] == ["D1"]
    assert contrib["permissions_ask"] == []
    assert hook_signature({"matcher": "A"}) in contrib["hooks_signatures"]
    assert hook_signature({"matcher": "B"}) in contrib["hooks_signatures"]


def test_strip_owned_removes_owned_permissions_and_hooks() -> None:
    settings = {
        "permissions": {
            "allow": ["user-read", "ours-1"],
            "deny": ["ours-d"],
        },
        "hooks": {
            "PostToolUse": [
                {"matcher": "USER"},
                {"matcher": "OURS"},
            ]
        },
        "model": "opus",
    }
    owned = {
        "permissions_allow": ["ours-1"],
        "permissions_deny": ["ours-d"],
        "permissions_ask": [],
        "hooks_signatures": [hook_signature({"matcher": "OURS"})],
    }
    result = strip_owned(settings, owned)
    assert result["permissions"] == {"allow": ["user-read"]}
    assert result["hooks"] == {"PostToolUse": [{"matcher": "USER"}]}
    assert result["model"] == "opus"  # untouched


def test_strip_owned_drops_empty_containers() -> None:
    settings = {
        "permissions": {"allow": ["only-ours"]},
        "hooks": {"PostToolUse": [{"matcher": "OURS"}]},
    }
    owned = {
        "permissions_allow": ["only-ours"],
        "permissions_deny": [],
        "permissions_ask": [],
        "hooks_signatures": [hook_signature({"matcher": "OURS"})],
    }
    result = strip_owned(settings, owned)
    assert "permissions" not in result
    assert "hooks" not in result


def test_strip_owned_no_op_when_nothing_owned() -> None:
    settings = {"permissions": {"allow": ["x"]}}
    result = strip_owned(
        settings,
        {
            "permissions_allow": [],
            "permissions_deny": [],
            "permissions_ask": [],
            "hooks_signatures": [],
        },
    )
    assert result == settings
