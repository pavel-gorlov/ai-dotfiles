"""Unit tests for ai_dotfiles.core.manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.manifest import (
    add_packages,
    get_link_mode,
    get_packages,
    get_targets,
    read_manifest,
    remove_packages,
    write_manifest,
)


def test_read_missing_file(tmp_path: Path) -> None:
    assert read_manifest(tmp_path / "missing.json") == {"packages": []}


def test_read_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"packages": ["@python"], "stack": "backend"}))
    assert read_manifest(path) == {"packages": ["@python"], "stack": "backend"}


def test_read_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text("{not valid json")
    with pytest.raises(ConfigError):
        read_manifest(path)


def test_read_non_object_raises(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text("[]")
    with pytest.raises(ConfigError):
        read_manifest(path)


def test_write_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    assert json.loads(path.read_text()) == {"packages": ["@python"]}


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "m.json"
    write_manifest(path, {"packages": []})
    assert path.exists()


def test_write_indent_and_newline(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    text = path.read_text()
    assert text.endswith("\n")
    assert '  "packages"' in text  # indent=2


def test_get_packages_empty(tmp_path: Path) -> None:
    assert get_packages(tmp_path / "missing.json") == []


def test_get_packages_populated(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python", "skill:x"]})
    assert get_packages(path) == ["@python", "skill:x"]


def test_add_packages_new(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": []})
    added = add_packages(path, ["@python", "skill:x"])
    assert added == ["@python", "skill:x"]
    assert get_packages(path) == ["@python", "skill:x"]


def test_add_packages_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    added = add_packages(path, ["@python"])
    assert added == []
    assert get_packages(path) == ["@python"]


def test_add_packages_mixed(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    added = add_packages(path, ["@python", "skill:x", "skill:x"])
    assert added == ["skill:x"]
    assert get_packages(path) == ["@python", "skill:x"]


def test_add_packages_to_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "m.json"
    added = add_packages(path, ["@python"])
    assert added == ["@python"]
    assert path.exists()
    assert get_packages(path) == ["@python"]


def test_remove_packages_existing(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python", "skill:x"]})
    removed = remove_packages(path, ["@python"])
    assert removed == ["@python"]
    assert get_packages(path) == ["skill:x"]


def test_remove_packages_missing(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    removed = remove_packages(path, ["skill:nope"])
    assert removed == []
    assert get_packages(path) == ["@python"]


def test_remove_packages_mixed(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python", "skill:x"]})
    removed = remove_packages(path, ["@python", "skill:nope"])
    assert removed == ["@python"]
    assert get_packages(path) == ["skill:x"]


# ---------------------------------------------------------------------------
# get_targets
# ---------------------------------------------------------------------------


def test_get_targets_missing_file_defaults_to_claude(tmp_path: Path) -> None:
    assert get_targets(tmp_path / "missing.json") == ["claude"]


def test_get_targets_no_targets_field_defaults_to_claude(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    assert get_targets(path) == ["claude"]


def test_get_targets_explicit_list(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "targets": ["claude", "codex"]})
    assert get_targets(path) == ["claude", "codex"]


def test_get_targets_empty_list_is_honoured(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "targets": []})
    assert get_targets(path) == []


def test_get_targets_non_list_raises(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "targets": "codex"})
    with pytest.raises(ConfigError):
        get_targets(path)


def test_get_targets_non_string_items_raise(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "targets": ["claude", 3]})
    with pytest.raises(ConfigError):
        get_targets(path)


# ── get_link_mode ─────────────────────────────────────────────────────────


def test_get_link_mode_absent_defaults_to_symlink(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": ["@python"]})
    assert get_link_mode(path) == "symlink"


def test_get_link_mode_missing_file_defaults_to_symlink(tmp_path: Path) -> None:
    assert get_link_mode(tmp_path / "nope.json") == "symlink"


def test_get_link_mode_explicit_symlink(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "link_mode": "symlink"})
    assert get_link_mode(path) == "symlink"


def test_get_link_mode_explicit_copy(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "link_mode": "copy"})
    assert get_link_mode(path) == "copy"


def test_get_link_mode_unknown_value_raises(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "link_mode": "hardlink"})
    with pytest.raises(ConfigError):
        get_link_mode(path)


def test_get_link_mode_non_string_raises(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    write_manifest(path, {"packages": [], "link_mode": True})
    with pytest.raises(ConfigError):
        get_link_mode(path)
