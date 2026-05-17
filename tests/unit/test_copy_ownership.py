"""Unit tests for ai_dotfiles.core.copy_ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.copy_ownership import (
    OWNERSHIP_FILENAME,
    delete_copy_ownership,
    load_copy_ownership,
    relative_label,
    save_copy_ownership,
)
from ai_dotfiles.core.errors import ConfigError


def test_load_missing_returns_empty_set(tmp_path: Path) -> None:
    assert load_copy_ownership(tmp_path) == set()


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    entries = {"skills/foo", "agents/bar.md"}
    save_copy_ownership(tmp_path, entries)
    assert (tmp_path / OWNERSHIP_FILENAME).is_file()
    assert load_copy_ownership(tmp_path) == entries


def test_save_empty_set_deletes_sidecar(tmp_path: Path) -> None:
    save_copy_ownership(tmp_path, {"skills/foo"})
    assert (tmp_path / OWNERSHIP_FILENAME).is_file()
    save_copy_ownership(tmp_path, set())
    assert not (tmp_path / OWNERSHIP_FILENAME).exists()


def test_delete_is_silent_when_absent(tmp_path: Path) -> None:
    delete_copy_ownership(tmp_path)  # must not raise


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    (tmp_path / OWNERSHIP_FILENAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_copy_ownership(tmp_path)


def test_load_non_object_raises(tmp_path: Path) -> None:
    (tmp_path / OWNERSHIP_FILENAME).write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_copy_ownership(tmp_path)


def test_load_bad_entries_type_raises(tmp_path: Path) -> None:
    (tmp_path / OWNERSHIP_FILENAME).write_text('{"entries": [1, 2]}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_copy_ownership(tmp_path)


def test_relative_label_uses_posix_separators(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    target = claude / "skills" / "code-review"
    assert relative_label(target, claude) == "skills/code-review"


def test_relative_label_outside_falls_back_to_str(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    outside = tmp_path / "elsewhere" / "thing"
    assert relative_label(outside, claude) == str(outside)
