"""Unit tests for ai_dotfiles.core.mcp_merge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.mcp_merge import (
    assemble_mcp_servers,
    backup_mcp_json,
    collect_mcp_fragments,
    derive_mcp_permissions,
    detect_collisions,
    load_mcp_fragment,
    merge_with_existing_mcp,
    strip_mcp_meta,
    warn_missing_npm_requires,
    warn_unset_env_vars,
    write_mcp_json,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _fragment(domain: str, servers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "_domain": domain,
        "_description": f"{domain} domain",
        "mcpServers": servers,
    }


# ---------------------------------------------------------------------------
# load / strip
# ---------------------------------------------------------------------------


def test_load_mcp_fragment_existing(tmp_path: Path) -> None:
    fragment = _fragment("x", {"s": {"command": "echo"}})
    path = tmp_path / "mcp.fragment.json"
    _write_json(path, fragment)
    assert load_mcp_fragment(path) == fragment


def test_load_mcp_fragment_missing_returns_empty(tmp_path: Path) -> None:
    assert load_mcp_fragment(tmp_path / "nope.json") == {}


def test_load_mcp_fragment_invalid_json_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_mcp_fragment(path)


def test_load_mcp_fragment_not_object_raises(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_mcp_fragment(path)


def test_strip_mcp_meta_removes_underscored_keys() -> None:
    fragment = {
        "_domain": "x",
        "_description": "desc",
        "_requires": {"npm": ["pkg"]},
        "mcpServers": {"s": {"command": "echo"}},
    }
    result = strip_mcp_meta(fragment)
    assert "_domain" not in result
    assert "_description" not in result
    assert "_requires" not in result
    assert result["mcpServers"] == {"s": {"command": "echo"}}


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


def test_collect_mcp_fragments_only_domain_specifiers(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    (catalog / "foo").mkdir(parents=True)
    _write_json(catalog / "foo" / "mcp.fragment.json", _fragment("foo", {}))
    (catalog / "skills" / "sk").mkdir(parents=True)
    # standalone skill:sk has no mcp fragment; shouldn't be picked up.

    packages = ["@foo", "skill:sk", "agent:a"]
    result = collect_mcp_fragments(packages, catalog)
    assert len(result) == 1
    assert result[0][0] == "foo"
    assert result[0][1] == catalog / "foo" / "mcp.fragment.json"


def test_collect_mcp_fragments_missing_file_skipped(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    (catalog / "foo").mkdir(parents=True)
    # No mcp.fragment.json — domain has no MCP servers.

    assert collect_mcp_fragments(["@foo"], catalog) == []


def test_collect_mcp_fragments_preserves_package_order(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    for name in ("alpha", "beta", "gamma"):
        (catalog / name).mkdir(parents=True)
        _write_json(catalog / name / "mcp.fragment.json", _fragment(name, {}))
    result = collect_mcp_fragments(["@gamma", "@alpha", "@beta"], catalog)
    assert [d for d, _ in result] == ["gamma", "alpha", "beta"]


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------


def test_assemble_mcp_servers_single_domain(tmp_path: Path) -> None:
    path = tmp_path / "mcp.fragment.json"
    _write_json(path, _fragment("foo", {"s": {"command": "echo"}}))
    servers, ownership = assemble_mcp_servers([("foo", path)])
    assert servers == {"s": {"command": "echo"}}
    assert ownership == {"s": ["foo"]}


def test_assemble_mcp_servers_multi_domain_no_overlap(tmp_path: Path) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _write_json(path_a, _fragment("a", {"sa": {"command": "echo"}}))
    _write_json(path_b, _fragment("b", {"sb": {"command": "ls"}}))
    servers, ownership = assemble_mcp_servers([("a", path_a), ("b", path_b)])
    assert servers == {
        "sa": {"command": "echo"},
        "sb": {"command": "ls"},
    }
    assert ownership == {"sa": ["a"], "sb": ["b"]}


def test_assemble_mcp_servers_conflict_last_wins_ownership_records_both(
    tmp_path: Path,
) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _write_json(path_a, _fragment("a", {"s": {"command": "echo"}}))
    _write_json(path_b, _fragment("b", {"s": {"command": "overridden"}}))
    servers, ownership = assemble_mcp_servers([("a", path_a), ("b", path_b)])
    assert servers == {"s": {"command": "overridden"}}
    assert ownership == {"s": ["a", "b"]}


def test_assemble_mcp_servers_preserves_http_type_url_headers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "http.json"
    server = {
        "type": "http",
        "url": "${API_BASE_URL:-https://api.example.com}/mcp",
        "headers": {"Authorization": "Bearer ${API_KEY}"},
    }
    _write_json(path, _fragment("h", {"api": server}))
    servers, _ = assemble_mcp_servers([("h", path)])
    assert servers["api"] == server


def test_assemble_mcp_servers_rejects_non_object_mcp_servers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.json"
    _write_json(path, {"_domain": "x", "mcpServers": [1, 2, 3]})
    with pytest.raises(ConfigError):
        assemble_mcp_servers([("x", path)])


def test_assemble_mcp_servers_rejects_non_object_server(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    _write_json(path, {"_domain": "x", "mcpServers": {"s": "not-a-dict"}})
    with pytest.raises(ConfigError):
        assemble_mcp_servers([("x", path)])


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------


def test_derive_mcp_permissions_produces_wildcards() -> None:
    assert derive_mcp_permissions(["foo", "bar"]) == [
        "mcp__foo__*",
        "mcp__bar__*",
    ]


def test_derive_mcp_permissions_dedup() -> None:
    assert derive_mcp_permissions(["foo", "foo", "bar"]) == [
        "mcp__foo__*",
        "mcp__bar__*",
    ]


# ---------------------------------------------------------------------------
# merge with existing
# ---------------------------------------------------------------------------


def test_merge_preserves_user_servers() -> None:
    existing = {"mcpServers": {"user-srv": {"command": "user"}}}
    result = merge_with_existing_mcp(
        new_servers={"domain-srv": {"command": "domain"}},
        existing=existing,
        previous_ownership={},
    )
    assert result["mcpServers"]["user-srv"] == {"command": "user"}
    assert result["mcpServers"]["domain-srv"] == {"command": "domain"}


def test_merge_drops_stale_domain_servers() -> None:
    existing = {
        "mcpServers": {
            "user-srv": {"command": "user"},
            "stale": {"command": "old"},
        }
    }
    result = merge_with_existing_mcp(
        new_servers={},
        existing=existing,
        previous_ownership={"stale": ["somedomain"]},
    )
    assert "stale" not in result["mcpServers"]
    assert result["mcpServers"]["user-srv"] == {"command": "user"}


def test_merge_updates_changed_domain_servers_when_in_prev_ownership() -> None:
    existing = {"mcpServers": {"s": {"command": "old"}}}
    result = merge_with_existing_mcp(
        new_servers={"s": {"command": "new"}},
        existing=existing,
        previous_ownership={"s": ["domainA"]},
    )
    assert result["mcpServers"]["s"] == {"command": "new"}


def test_merge_first_time_collision_user_wins() -> None:
    existing = {"mcpServers": {"s": {"command": "user-version"}}}
    result = merge_with_existing_mcp(
        new_servers={"s": {"command": "domain-version"}},
        existing=existing,
        previous_ownership={},
    )
    assert result["mcpServers"]["s"] == {"command": "user-version"}


def test_merge_repeat_collision_domain_wins() -> None:
    existing = {"mcpServers": {"s": {"command": "prev-domain"}}}
    result = merge_with_existing_mcp(
        new_servers={"s": {"command": "new-domain"}},
        existing=existing,
        previous_ownership={"s": ["domainA"]},
    )
    assert result["mcpServers"]["s"] == {"command": "new-domain"}


def test_merge_preserves_non_mcp_top_level_keys() -> None:
    existing = {"mcpServers": {}, "customUserKey": "foo"}
    result = merge_with_existing_mcp(
        new_servers={"s": {"command": "x"}},
        existing=existing,
        previous_ownership={},
    )
    assert result["customUserKey"] == "foo"


# ---------------------------------------------------------------------------
# detect_collisions
# ---------------------------------------------------------------------------


def test_detect_collisions_returns_first_time_collisions_only() -> None:
    existing = {
        "mcpServers": {
            "user": {"command": "u"},
            "tracked": {"command": "t"},
        }
    }
    new_servers = {
        "user": {"command": "d"},
        "tracked": {"command": "d2"},
        "fresh": {"command": "d3"},
    }
    result = detect_collisions(
        new_servers, existing, previous_ownership={"tracked": ["d"]}
    )
    assert result == ["user"]


# ---------------------------------------------------------------------------
# write / backup
# ---------------------------------------------------------------------------


def test_write_mcp_json_indent_and_newline(tmp_path: Path) -> None:
    target = tmp_path / ".mcp.json"
    write_mcp_json({"mcpServers": {"s": {"command": "x"}}}, target)
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '  "mcpServers"' in text


def test_backup_mcp_json_no_source_returns_none(tmp_path: Path) -> None:
    assert backup_mcp_json(tmp_path / "missing.json", tmp_path / "bk", "p") is None


def test_backup_mcp_json_creates_copy(tmp_path: Path) -> None:
    src = tmp_path / ".mcp.json"
    src.write_text('{"mcpServers": {}}', encoding="utf-8")
    backup_root = tmp_path / "backup"
    result = backup_mcp_json(src, backup_root, "myproj")
    assert result is not None
    assert result.exists()
    assert result.parent == backup_root / ".claude-mcp" / "myproj"
    assert result.read_text(encoding="utf-8") == '{"mcpServers": {}}'


def test_backup_mcp_json_timestamps_unique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / ".mcp.json"
    src.write_text("{}", encoding="utf-8")
    backup_root = tmp_path / "backup"

    monkeypatch.setattr(
        "ai_dotfiles.core.mcp_merge._timestamp",
        lambda: "2026-04-22T14-33-07Z",
    )

    first = backup_mcp_json(src, backup_root, "p")
    second = backup_mcp_json(src, backup_root, "p")
    third = backup_mcp_json(src, backup_root, "p")
    assert first is not None and second is not None and third is not None
    assert first != second != third
    assert first.exists() and second.exists() and third.exists()


# ---------------------------------------------------------------------------
# env var warnings
# ---------------------------------------------------------------------------


def test_warn_unset_env_vars_finds_pattern_once_per_var() -> None:
    warnings: list[str] = []
    servers = {
        "a": {"env": {"X": "${FOO}"}, "args": ["--token", "${FOO}"]},
        "b": {"env": {"Y": "${FOO}"}},
    }
    warn_unset_env_vars(servers, warnings.append, environ={})
    assert len(warnings) == 1
    assert "FOO" in warnings[0]


def test_warn_unset_env_vars_skips_tokens_with_default() -> None:
    warnings: list[str] = []
    servers = {"a": {"url": "${FOO:-fallback}"}}
    warn_unset_env_vars(servers, warnings.append, environ={})
    assert warnings == []


def test_warn_unset_env_vars_silent_when_set() -> None:
    warnings: list[str] = []
    servers = {"a": {"env": {"X": "${FOO}"}}}
    warn_unset_env_vars(servers, warnings.append, environ={"FOO": "value"})
    assert warnings == []


def test_warn_unset_env_vars_ignores_non_matching_tokens() -> None:
    warnings: list[str] = []
    servers = {"a": {"args": ["$literal", "${env:FOO}"]}}
    # ${env:FOO} is NOT Claude Code syntax — should not match our regex.
    warn_unset_env_vars(servers, warnings.append, environ={})
    assert warnings == []


# ---------------------------------------------------------------------------
# npm requires warnings
# ---------------------------------------------------------------------------


def test_warn_missing_npm_requires_no_package_json_silent(tmp_path: Path) -> None:
    warnings: list[str] = []
    frag = tmp_path / "f.json"
    _write_json(frag, {"_domain": "x", "_requires": {"npm": ["foo"]}})
    warn_missing_npm_requires([("x", frag)], tmp_path, warnings.append)
    assert warnings == []


def test_warn_missing_npm_requires_flags_missing_dep(tmp_path: Path) -> None:
    warnings: list[str] = []
    frag = tmp_path / "f.json"
    _write_json(frag, {"_domain": "x", "_requires": {"npm": ["@foo/bar"]}})
    _write_json(
        tmp_path / "package.json",
        {"devDependencies": {"@other/thing": "1.0.0"}},
    )
    warn_missing_npm_requires([("x", frag)], tmp_path, warnings.append)
    assert len(warnings) == 1
    assert "@foo/bar" in warnings[0]
    assert "npm install -D @foo/bar" in warnings[0]


def test_warn_missing_npm_requires_present_silent(tmp_path: Path) -> None:
    warnings: list[str] = []
    frag = tmp_path / "f.json"
    _write_json(frag, {"_domain": "x", "_requires": {"npm": ["@foo/bar"]}})
    _write_json(
        tmp_path / "package.json",
        {"devDependencies": {"@foo/bar": "1.0.0"}},
    )
    warn_missing_npm_requires([("x", frag)], tmp_path, warnings.append)
    assert warnings == []


def test_warn_missing_npm_requires_reads_deps_and_peer(tmp_path: Path) -> None:
    warnings: list[str] = []
    frag = tmp_path / "f.json"
    _write_json(
        frag,
        {
            "_domain": "x",
            "_requires": {"npm": ["dep1", "peer1"]},
        },
    )
    _write_json(
        tmp_path / "package.json",
        {
            "dependencies": {"dep1": "1.0.0"},
            "peerDependencies": {"peer1": "2.0.0"},
        },
    )
    warn_missing_npm_requires([("x", frag)], tmp_path, warnings.append)
    assert warnings == []


def test_warn_missing_npm_requires_silent_on_bad_package_json(
    tmp_path: Path,
) -> None:
    warnings: list[str] = []
    frag = tmp_path / "f.json"
    _write_json(frag, {"_domain": "x", "_requires": {"npm": ["x"]}})
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    warn_missing_npm_requires([("x", frag)], tmp_path, warnings.append)
    # Malformed package.json → silent skip, not a hard error.
    assert warnings == []
