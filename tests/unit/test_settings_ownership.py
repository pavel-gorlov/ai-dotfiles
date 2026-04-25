"""Unit tests for ai_dotfiles.core.settings_ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.settings_ownership import (
    OWNERSHIP_FILENAME,
    delete_settings_ownership,
    is_empty,
    load_settings_ownership,
    ownership_path,
    save_settings_ownership,
)


def test_load_missing_returns_default(tmp_path: Path) -> None:
    data = load_settings_ownership(tmp_path)
    assert data == {
        "permissions_allow": [],
        "permissions_deny": [],
        "permissions_ask": [],
        "hooks_signatures": [],
    }


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    payload = {
        "permissions_allow": ["a", "b"],
        "permissions_deny": ["d"],
        "permissions_ask": [],
        "hooks_signatures": ["sig1", "sig2"],
    }
    save_settings_ownership(tmp_path, payload)
    assert load_settings_ownership(tmp_path) == {
        "permissions_allow": ["a", "b"],
        "permissions_deny": ["d"],
        "permissions_ask": [],
        "hooks_signatures": ["sig1", "sig2"],
    }


def test_save_writes_sorted_keys_and_dedup(tmp_path: Path) -> None:
    payload = {
        "permissions_allow": ["b", "a", "a"],
        "permissions_deny": [],
        "permissions_ask": [],
        "hooks_signatures": [],
    }
    save_settings_ownership(tmp_path, payload)
    raw = (tmp_path / OWNERSHIP_FILENAME).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["permissions_allow"] == ["a", "b"]


def test_delete_idempotent(tmp_path: Path) -> None:
    save_settings_ownership(
        tmp_path,
        {
            "permissions_allow": ["x"],
            "permissions_deny": [],
            "permissions_ask": [],
            "hooks_signatures": [],
        },
    )
    delete_settings_ownership(tmp_path)
    delete_settings_ownership(tmp_path)
    assert not ownership_path(tmp_path).exists()


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text("{broken", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings_ownership(tmp_path)


def test_load_wrong_value_type_raises(tmp_path: Path) -> None:
    ownership_path(tmp_path).write_text(
        json.dumps({"permissions_allow": "not-a-list"}), encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_settings_ownership(tmp_path)


def test_is_empty_detects_default_and_filled() -> None:
    assert is_empty(
        {
            "permissions_allow": [],
            "permissions_deny": [],
            "permissions_ask": [],
            "hooks_signatures": [],
        }
    )
    assert not is_empty(
        {
            "permissions_allow": ["x"],
            "permissions_deny": [],
            "permissions_ask": [],
            "hooks_signatures": [],
        }
    )
