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
    deep_merge_hooks,
    load_fragment,
    strip_meta,
    write_settings,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_fragment_existing(tmp_path: Path) -> None:
    fragment = {"_domain": "python", "hooks": {"PostToolUse": []}}
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


def test_strip_meta() -> None:
    fragment = {
        "_domain": "python",
        "_description": "Ruff",
        "hooks": {"PostToolUse": []},
        "env": {"FOO": "bar"},
    }
    result = strip_meta(fragment)
    assert "_domain" not in result
    assert "_description" not in result
    assert result == {"hooks": {"PostToolUse": []}, "env": {"FOO": "bar"}}
    # Original not mutated.
    assert "_domain" in fragment


def test_strip_meta_no_meta() -> None:
    fragment = {"hooks": {"PreToolUse": []}}
    assert strip_meta(fragment) == fragment


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
        {
            "_domain": "python",
            "_description": "Ruff",
            "hooks": {"PostToolUse": [{"cmd": "ruff"}]},
        },
    )
    result = assemble_settings([frag])
    assert "_domain" not in result
    assert "_description" not in result
    assert result == {"hooks": {"PostToolUse": [{"cmd": "ruff"}]}}


def test_assemble_multiple_fragments(tmp_path: Path) -> None:
    frag_py = tmp_path / "python" / "settings.fragment.json"
    _write_json(
        frag_py,
        {
            "_domain": "python",
            "hooks": {
                "PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"cmd": "ruff"}]}]
            },
        },
    )
    frag_go = tmp_path / "go" / "settings.fragment.json"
    _write_json(
        frag_go,
        {
            "_domain": "go",
            "hooks": {
                "PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"cmd": "gofmt"}]}],
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"cmd": "go-vet"}]}],
            },
        },
    )
    # Pass in non-sorted order to verify deterministic sort by path.
    result = assemble_settings([frag_py, frag_go])

    # Sorted path order: "go" dir sorts before "python" dir.
    assert result["hooks"]["PostToolUse"] == [
        {"matcher": "Edit|Write", "hooks": [{"cmd": "gofmt"}]},
        {"matcher": "Edit|Write", "hooks": [{"cmd": "ruff"}]},
    ]
    assert result["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [{"cmd": "go-vet"}]}
    ]

    # Deterministic: same input reversed yields same output.
    result_rev = assemble_settings([frag_go, frag_py])
    assert result == result_rev


def test_assemble_with_base(tmp_path: Path) -> None:
    frag = tmp_path / "python" / "settings.fragment.json"
    _write_json(
        frag,
        {"_domain": "python", "hooks": {"PostToolUse": [{"cmd": "ruff"}]}},
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
