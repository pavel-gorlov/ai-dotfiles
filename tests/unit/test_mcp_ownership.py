"""Unit tests for ai_dotfiles.core.mcp_ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.mcp_ownership import (
    OWNERSHIP_FILENAME,
    delete_ownership,
    load_ownership,
    ownership_path,
    save_ownership,
)


def test_ownership_path_matches_filename(tmp_path: Path) -> None:
    assert ownership_path(tmp_path).name == OWNERSHIP_FILENAME
    assert ownership_path(tmp_path).parent == tmp_path


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_ownership(tmp_path) == {}


def test_save_then_load_roundtrip_sorted_keys(tmp_path: Path) -> None:
    data = {"zulu": ["a"], "alpha": ["b", "c"], "mike": ["d"]}
    save_ownership(tmp_path, data)
    loaded = load_ownership(tmp_path)
    assert loaded == data

    raw = (tmp_path / OWNERSHIP_FILENAME).read_text(encoding="utf-8")
    # Keys written in sorted order for deterministic diffs.
    assert raw.index('"alpha"') < raw.index('"mike"') < raw.index('"zulu"')
    assert raw.endswith("\n")


def test_delete_idempotent(tmp_path: Path) -> None:
    save_ownership(tmp_path, {"s": ["d"]})
    delete_ownership(tmp_path)
    delete_ownership(tmp_path)  # must not raise
    assert not ownership_path(tmp_path).exists()


def test_save_atomic_does_not_leave_tmp_on_success(tmp_path: Path) -> None:
    save_ownership(tmp_path, {"s": ["d"]})
    tmp_sibling = ownership_path(tmp_path).with_suffix(
        ownership_path(tmp_path).suffix + ".tmp"
    )
    assert not tmp_sibling.exists()


def test_load_invalid_json_raises_config_error(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_ownership(tmp_path)


def test_load_wrong_top_level_shape_raises(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_ownership(tmp_path)


def test_load_wrong_value_shape_raises(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text(
        json.dumps({"server": "not-a-list"}), encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_ownership(tmp_path)


def test_load_wrong_value_element_type_raises(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text(
        json.dumps({"server": [1, 2]}), encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_ownership(tmp_path)


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "deeply" / "nested"
    save_ownership(nested, {"s": ["d"]})
    assert ownership_path(nested).exists()
