"""Unit tests for ai_dotfiles.core.codex_config.

Covers the four DoD areas: fragment translation (permissions / sandbox),
the hooks skip (ADR ai-1-5), ownership / strip, and composability — an
unrelated ``[mcp_servers]`` table must survive a settings write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomllib

from ai_dotfiles.core.codex_config import (
    MANAGED_TABLE,
    ConfigResult,
    build_managed_table,
    config_path,
    render_config_toml,
    strip_managed,
    translate_fragment,
    write_codex_config,
)
from ai_dotfiles.core.errors import ConfigError


def _write_fragment(directory: Path, name: str, data: dict[str, object]) -> Path:
    """Write a ``settings.fragment.json`` under ``directory/<name>/``."""
    domain_dir = directory / name
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / "settings.fragment.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _read_config(project_root: Path) -> dict[str, object]:
    """Parse the project ``.codex/config.toml`` into a dict."""
    with config_path(project_root).open("rb") as handle:
        return tomllib.load(handle)


# ── translate_fragment ────────────────────────────────────────────────


def test_translate_permissions_allow() -> None:
    fragment = {"permissions": {"allow": ["Bash(git diff:*)", "Bash(git log:*)"]}}
    translated, skipped = translate_fragment(fragment)
    assert translated == {
        "permissions": {"allow": ["Bash(git diff:*)", "Bash(git log:*)"]}
    }
    assert skipped == []


def test_translate_permissions_dedup_preserves_first_seen_order() -> None:
    fragment = {"permissions": {"allow": ["a", "b", "a", "c"]}}
    translated, _ = translate_fragment(fragment)
    assert translated["permissions"]["allow"] == ["a", "b", "c"]


def test_translate_permissions_deny_and_ask() -> None:
    fragment = {"permissions": {"deny": ["Bash(rm:*)"], "ask": ["Bash(curl:*)"]}}
    translated, _ = translate_fragment(fragment)
    assert translated == {
        "permissions": {"deny": ["Bash(rm:*)"], "ask": ["Bash(curl:*)"]}
    }


def test_translate_sandbox() -> None:
    fragment = {"sandbox": {"mode": "workspace-write", "network_access": False}}
    translated, skipped = translate_fragment(fragment)
    assert translated == {
        "sandbox": {"mode": "workspace-write", "network_access": False}
    }
    assert skipped == []


def test_translate_hooks_are_skipped_not_translated() -> None:
    fragment = {
        "permissions": {"allow": ["Bash(git:*)"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash"}]},
    }
    translated, skipped = translate_fragment(fragment)
    assert "hooks" not in translated
    assert translated == {"permissions": {"allow": ["Bash(git:*)"]}}
    assert skipped == ["hooks"]


def test_translate_empty_fragment_yields_nothing() -> None:
    assert translate_fragment({}) == ({}, [])


def test_translate_ignores_empty_permission_lists() -> None:
    translated, _ = translate_fragment({"permissions": {"allow": []}})
    assert translated == {}


# ── build_managed_table ───────────────────────────────────────────────


def test_build_managed_table_merges_two_domains(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    p1 = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g1"]}})
    p2 = _write_fragment(catalog, "python", {"permissions": {"allow": ["p1", "g1"]}})
    managed, skipped = build_managed_table([("gitflow", p1), ("python", p2)])
    # Concat + dedup across domains, first-seen order.
    assert managed == {"permissions": {"allow": ["g1", "p1"]}}
    assert skipped == {}


def test_build_managed_table_collects_skipped_hooks_per_domain(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    p1 = _write_fragment(
        catalog, "gitflow", {"hooks": {"PreToolUse": [{"matcher": "Bash"}]}}
    )
    p2 = _write_fragment(catalog, "python", {"permissions": {"allow": ["x"]}})
    managed, skipped = build_managed_table([("gitflow", p1), ("python", p2)])
    assert managed == {"permissions": {"allow": ["x"]}}
    assert skipped == {"gitflow": ["hooks"]}


def test_build_managed_table_sandbox_overlay_wins(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    p1 = _write_fragment(catalog, "a", {"sandbox": {"mode": "read-only"}})
    p2 = _write_fragment(catalog, "b", {"sandbox": {"mode": "workspace-write"}})
    managed, _ = build_managed_table([("a", p1), ("b", p2)])
    assert managed["sandbox"] == {"mode": "workspace-write"}


# ── render_config_toml ────────────────────────────────────────────────


def test_render_managed_block_has_markers() -> None:
    text = render_config_toml({}, {"permissions": {"allow": ["x"]}})
    assert "# >>> ai-dotfiles managed (config)" in text
    assert "# <<< ai-dotfiles managed (config) <<<" in text
    assert "[ai_dotfiles.permissions]" in text


def test_render_empty_managed_with_no_other_is_empty_string() -> None:
    assert render_config_toml({}, {}) == ""


def test_render_preserves_unrelated_table() -> None:
    existing = {"mcp_servers": {"fs": {"command": "npx"}}}
    text = render_config_toml(existing, {"permissions": {"allow": ["x"]}})
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"] == {"fs": {"command": "npx"}}
    assert parsed["ai_dotfiles"] == {"permissions": {"allow": ["x"]}}


def test_render_replaces_old_managed_table() -> None:
    existing = {"ai_dotfiles": {"permissions": {"allow": ["stale"]}}}
    text = render_config_toml(existing, {"permissions": {"allow": ["fresh"]}})
    parsed = tomllib.loads(text)
    assert parsed["ai_dotfiles"]["permissions"]["allow"] == ["fresh"]


# ── write_codex_config — end to end ───────────────────────────────────


def test_write_creates_config(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    result = write_codex_config(project, [("gitflow", frag)])
    assert result.status == "created"
    assert result.skipped_keys == {}
    parsed = _read_config(project)
    assert parsed["ai_dotfiles"] == {"permissions": {"allow": ["g"]}}


def test_write_reports_skipped_hooks(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_fragment(
        catalog,
        "gitflow",
        {
            "permissions": {"allow": ["g"]},
            "hooks": {"PreToolUse": [{"matcher": "Bash"}]},
        },
    )
    result = write_codex_config(project, [("gitflow", frag)])
    assert result.skipped_keys == {"gitflow": ["hooks"]}
    # The skipped key is not written into the config.
    assert "hooks" not in _read_config(project)["ai_dotfiles"]


def test_write_second_run_updates(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    assert write_codex_config(project, [("gitflow", frag)]).status == "created"
    assert write_codex_config(project, [("gitflow", frag)]).status == "updated"


def test_write_empty_creates_nothing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    result = write_codex_config(project, [])
    assert result.status == "updated"
    assert not config_path(project).exists()


def test_write_invalid_existing_toml_raises(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text("this is = not valid = toml\n", encoding="utf-8")
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    with pytest.raises(ConfigError, match="Invalid TOML"):
        write_codex_config(project, [("gitflow", frag)])


# ── composability — the critical constraint ───────────────────────────


def test_write_preserves_unrelated_mcp_servers_table(tmp_path: Path) -> None:
    """A future ai-15 [mcp_servers] table must survive a settings write."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    # Simulate ai-15 having already written an MCP table plus a user table.
    cfg.write_text(
        "[mcp_servers.filesystem]\n"
        'command = "npx"\n'
        'args = ["-y", "@modelcontextprotocol/server-filesystem"]\n'
        "\n"
        "[user_table]\n"
        'key = "value"\n',
        encoding="utf-8",
    )
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    write_codex_config(project, [("gitflow", frag)])

    parsed = _read_config(project)
    assert parsed["mcp_servers"]["filesystem"]["command"] == "npx"
    assert parsed["mcp_servers"]["filesystem"]["args"] == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
    ]
    assert parsed["user_table"] == {"key": "value"}
    assert parsed["ai_dotfiles"] == {"permissions": {"allow": ["g"]}}


def test_rewrite_does_not_duplicate_managed_table(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag1 = _write_fragment(catalog, "a", {"permissions": {"allow": ["a"]}})
    frag2 = _write_fragment(catalog, "b", {"permissions": {"allow": ["b"]}})
    write_codex_config(project, [("a", frag1)])
    write_codex_config(project, [("b", frag2)])
    text = config_path(project).read_text(encoding="utf-8")
    # Exactly one managed block, holding only the second run's content.
    assert text.count("# >>> ai-dotfiles managed (config)") == 1
    assert _read_config(project)["ai_dotfiles"] == {"permissions": {"allow": ["b"]}}


# ── strip_managed — the remove-side analogue ──────────────────────────


def test_strip_removes_only_managed_table(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.fs]\ncommand = "npx"\n', encoding="utf-8")
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    write_codex_config(project, [("gitflow", frag)])

    assert strip_managed(project) is True
    parsed = _read_config(project)
    assert MANAGED_TABLE not in parsed
    # The unrelated MCP table survives the strip.
    assert parsed["mcp_servers"]["fs"]["command"] == "npx"


def test_strip_deletes_file_when_only_managed_content(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    write_codex_config(project, [("gitflow", frag)])
    assert config_path(project).exists()

    assert strip_managed(project) is True
    assert not config_path(project).exists()


def test_strip_noop_when_no_file(tmp_path: Path) -> None:
    assert strip_managed(tmp_path / "project") is False


def test_strip_noop_when_no_managed_table(tmp_path: Path) -> None:
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.fs]\ncommand = "npx"\n', encoding="utf-8")
    assert strip_managed(project) is False
    # Untouched.
    assert "mcp_servers" in _read_config(project)


def test_write_then_remove_to_empty_manifest_strips_region(tmp_path: Path) -> None:
    """Rebuilding from an empty fragment list strips the managed region."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_fragment(catalog, "gitflow", {"permissions": {"allow": ["g"]}})
    write_codex_config(project, [("gitflow", frag)])
    result = write_codex_config(project, [])
    assert result.status == "removed"
    assert not config_path(project).exists()


# ── ConfigResult ──────────────────────────────────────────────────────


def test_config_result_equality() -> None:
    assert ConfigResult("created") == ConfigResult("created", {})
    assert ConfigResult("created") != ConfigResult("updated")
    assert ConfigResult("created", {"d": ["hooks"]}) != ConfigResult("created")
