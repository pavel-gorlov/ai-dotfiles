"""Unit tests for ai_dotfiles.core.codex_mcp_ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.codex_mcp_ownership import (
    delete_mcp_ownership,
    load_mcp_ownership,
    mcp_ownership_path,
    save_mcp_ownership,
)
from ai_dotfiles.core.errors import ConfigError


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_mcp_ownership(tmp_path) == {}


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    save_mcp_ownership(tmp_path, {"fs": ["a"], "web": ["b", "c"]})
    assert load_mcp_ownership(tmp_path) == {"fs": ["a"], "web": ["b", "c"]}


def test_save_sorts_keys(tmp_path: Path) -> None:
    save_mcp_ownership(tmp_path, {"z": ["d"], "a": ["d"]})
    text = mcp_ownership_path(tmp_path).read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"z"')


def test_ownership_path_is_under_dot_codex(tmp_path: Path) -> None:
    path = mcp_ownership_path(tmp_path)
    assert path.parent.name == ".codex"
    assert path.name == ".ai-dotfiles-mcp-ownership.json"


def test_delete_removes_file(tmp_path: Path) -> None:
    save_mcp_ownership(tmp_path, {"fs": ["a"]})
    assert mcp_ownership_path(tmp_path).exists()
    delete_mcp_ownership(tmp_path)
    assert not mcp_ownership_path(tmp_path).exists()


def test_delete_silent_when_absent(tmp_path: Path) -> None:
    delete_mcp_ownership(tmp_path)  # no exception


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    path = mcp_ownership_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        load_mcp_ownership(tmp_path)


def test_load_non_object_raises(tmp_path: Path) -> None:
    path = mcp_ownership_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_mcp_ownership(tmp_path)


def test_load_malformed_value_raises(tmp_path: Path) -> None:
    path = mcp_ownership_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"fs": "not-a-list"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="list of strings"):
        load_mcp_ownership(tmp_path)
