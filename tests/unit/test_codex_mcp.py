"""Unit tests for the Codex ``[mcp_servers]`` writer (ai-15).

Covers the DoD areas: ``mcp.fragment.json`` -> ``[mcp_servers]``
translation, coexistence with the ai-14 ``[ai_dotfiles]`` settings
region in one ``config.toml``, and ownership / strip (user-defined
servers survive ``remove``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomllib

from ai_dotfiles.core.codex_config import (
    MCP_TABLE,
    McpResult,
    build_mcp_table,
    config_path,
    strip_codex_mcp,
    translate_mcp_server,
    write_codex_config,
    write_codex_mcp,
)
from ai_dotfiles.core.codex_mcp_ownership import (
    load_mcp_ownership,
    mcp_ownership_path,
)
from ai_dotfiles.core.errors import ConfigError


def _write_mcp_fragment(directory: Path, name: str, servers: dict[str, object]) -> Path:
    """Write an ``mcp.fragment.json`` under ``directory/<name>/``."""
    domain_dir = directory / name
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / "mcp.fragment.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return path


def _write_settings_fragment(
    directory: Path, name: str, data: dict[str, object]
) -> Path:
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


# ── translate_mcp_server ──────────────────────────────────────────────


def test_translate_keeps_command_args_env() -> None:
    server = {
        "command": "npx",
        "args": ["@playwright/mcp@latest", "--isolated"],
        "env": {"TOKEN": "x"},
    }
    assert translate_mcp_server(server) == server


def test_translate_drops_none_values() -> None:
    # TOML has no null — a fragment ``null`` means "unset" -> absent key.
    server = {"command": "npx", "url": None, "args": ["a"]}
    assert translate_mcp_server(server) == {"command": "npx", "args": ["a"]}


def test_translate_empty_server() -> None:
    assert translate_mcp_server({}) == {}


# ── build_mcp_table ───────────────────────────────────────────────────


def test_build_mcp_table_single_domain(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    frag = _write_mcp_fragment(
        catalog, "playwright-e2e", {"playwright": {"command": "npx"}}
    )
    servers, ownership = build_mcp_table([("playwright-e2e", frag)])
    assert servers == {"playwright": {"command": "npx"}}
    assert ownership == {"playwright": ["playwright-e2e"]}


def test_build_mcp_table_two_domains(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    p1 = _write_mcp_fragment(catalog, "a", {"fs": {"command": "fs-server"}})
    p2 = _write_mcp_fragment(catalog, "b", {"web": {"command": "web-server"}})
    servers, ownership = build_mcp_table([("a", p1), ("b", p2)])
    assert servers == {
        "fs": {"command": "fs-server"},
        "web": {"command": "web-server"},
    }
    assert ownership == {"fs": ["a"], "web": ["b"]}


# ── write_codex_mcp — end to end ──────────────────────────────────────


def test_write_creates_mcp_servers_table(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(
        catalog,
        "playwright-e2e",
        {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}},
    )
    result = write_codex_mcp(project, [("playwright-e2e", frag)])
    assert result == McpResult("created")
    parsed = _read_config(project)
    assert parsed[MCP_TABLE]["playwright"] == {
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    }


def test_write_records_ownership(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])
    assert load_mcp_ownership(project) == {"fs": ["a"]}


def test_write_second_run_updates(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    assert write_codex_mcp(project, [("a", frag)]).status == "created"
    assert write_codex_mcp(project, [("a", frag)]).status == "updated"


def test_write_empty_creates_nothing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    result = write_codex_mcp(project, [])
    assert result.status == "updated"
    assert not config_path(project).exists()


def test_write_invalid_existing_toml_raises(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text("broken = = toml\n", encoding="utf-8")
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    with pytest.raises(ConfigError, match="Invalid TOML"):
        write_codex_mcp(project, [("a", frag)])


# ── coexistence with the ai-14 [ai_dotfiles] region ───────────────────


def test_mcp_write_preserves_ai_dotfiles_region(tmp_path: Path) -> None:
    """The settings region (ai-14) survives an MCP write."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    settings = _write_settings_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git:*)"]}}
    )
    write_codex_config(project, [("gitflow", settings)])

    mcp = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", mcp)])

    parsed = _read_config(project)
    assert parsed["ai_dotfiles"] == {"permissions": {"allow": ["Bash(git:*)"]}}
    assert parsed[MCP_TABLE]["fs"] == {"command": "x"}


def test_settings_write_preserves_mcp_region(tmp_path: Path) -> None:
    """The MCP region (ai-15) survives a settings write — order-independent."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    mcp = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", mcp)])

    settings = _write_settings_fragment(
        catalog, "gitflow", {"sandbox": {"mode": "read-only"}}
    )
    write_codex_config(project, [("gitflow", settings)])

    parsed = _read_config(project)
    assert parsed[MCP_TABLE]["fs"] == {"command": "x"}
    assert parsed["ai_dotfiles"] == {"sandbox": {"mode": "read-only"}}


def test_both_regions_round_trip_repeatedly(tmp_path: Path) -> None:
    """Repeated interleaved writes never duplicate or drop either region."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    settings = _write_settings_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["p"]}}
    )
    mcp = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})

    write_codex_config(project, [("gitflow", settings)])
    write_codex_mcp(project, [("a", mcp)])
    write_codex_config(project, [("gitflow", settings)])
    write_codex_mcp(project, [("a", mcp)])

    parsed = _read_config(project)
    assert parsed["ai_dotfiles"] == {"permissions": {"allow": ["p"]}}
    assert parsed[MCP_TABLE] == {"fs": {"command": "x"}}


# ── ownership / strip — user-defined servers survive ──────────────────


def test_user_authored_server_survives_write(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.my-server]\ncommand = "user-cmd"\n', encoding="utf-8")
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])

    parsed = _read_config(project)
    assert parsed[MCP_TABLE]["my-server"] == {"command": "user-cmd"}
    assert parsed[MCP_TABLE]["fs"] == {"command": "x"}
    # The user server is not claimed.
    assert load_mcp_ownership(project) == {"fs": ["a"]}


def test_collision_keeps_user_version(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.fs]\ncommand = "user-fs"\n', encoding="utf-8")
    # Domain 'a' declares a server named 'fs' too — first-time collision.
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "domain-fs"}})
    result = write_codex_mcp(project, [("a", frag)])

    assert result.collisions == ["fs"]
    assert _read_config(project)[MCP_TABLE]["fs"] == {"command": "user-fs"}
    # A collided name is never claimed.
    assert load_mcp_ownership(project) == {}


def test_remove_strips_domain_servers_keeps_user(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.user-srv]\ncommand = "user-cmd"\n', encoding="utf-8")
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])

    # Remove: rebuild from an empty fragment list (domain gone).
    result = write_codex_mcp(project, [])
    assert result.status == "removed"

    parsed = _read_config(project)
    assert "fs" not in parsed[MCP_TABLE]
    assert parsed[MCP_TABLE]["user-srv"] == {"command": "user-cmd"}
    # Ownership cleared — nothing domain-owned remains.
    assert not mcp_ownership_path(project).exists()


def test_remove_deletes_file_when_only_domain_servers(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])
    assert config_path(project).exists()

    write_codex_mcp(project, [])
    assert not config_path(project).exists()
    assert not mcp_ownership_path(project).exists()


def test_strip_codex_mcp_removes_only_owned(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.user-srv]\ncommand = "u"\n', encoding="utf-8")
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])

    assert strip_codex_mcp(project) is True
    parsed = _read_config(project)
    assert "fs" not in parsed[MCP_TABLE]
    assert parsed[MCP_TABLE]["user-srv"] == {"command": "u"}
    assert not mcp_ownership_path(project).exists()


def test_strip_codex_mcp_noop_when_no_ownership(tmp_path: Path) -> None:
    project = tmp_path / "project"
    cfg = config_path(project)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.fs]\ncommand = "x"\n', encoding="utf-8")
    assert strip_codex_mcp(project) is False
    # Untouched.
    assert "fs" in _read_config(project)[MCP_TABLE]


def test_strip_codex_mcp_noop_when_no_file(tmp_path: Path) -> None:
    assert strip_codex_mcp(tmp_path / "project") is False


def test_strip_codex_mcp_deletes_file_when_empty(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(catalog, "a", {"fs": {"command": "x"}})
    write_codex_mcp(project, [("a", frag)])
    assert strip_codex_mcp(project) is True
    assert not config_path(project).exists()


# ── stale domain server dropped on next write ─────────────────────────


def test_stale_domain_server_dropped_on_rewrite(tmp_path: Path) -> None:
    """A server removed from a domain fragment is dropped on the next write."""
    catalog = tmp_path / "catalog"
    project = tmp_path / "project"
    frag = _write_mcp_fragment(
        catalog, "a", {"fs": {"command": "x"}, "web": {"command": "w"}}
    )
    write_codex_mcp(project, [("a", frag)])
    assert set(_read_config(project)[MCP_TABLE]) == {"fs", "web"}

    # Domain 'a' now declares only 'fs'.
    frag.write_text(
        json.dumps({"mcpServers": {"fs": {"command": "x"}}}), encoding="utf-8"
    )
    write_codex_mcp(project, [("a", frag)])
    assert set(_read_config(project)[MCP_TABLE]) == {"fs"}
    assert load_mcp_ownership(project) == {"fs": ["a"]}


# ── McpResult ─────────────────────────────────────────────────────────


def test_mcp_result_equality() -> None:
    assert McpResult("created") == McpResult("created", [])
    assert McpResult("created") != McpResult("updated")
    assert McpResult("created", ["fs"]) != McpResult("created")
