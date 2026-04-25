"""Unit tests for ai_dotfiles.core.manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.core.manifest import (
    add_packages,
    get_packages,
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
