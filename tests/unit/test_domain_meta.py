"""Unit tests for ai_dotfiles.core.domain_meta."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.domain_meta import DomainMeta, read_domain_meta
from ai_dotfiles.core.errors import ConfigError


def _write_meta(catalog: Path, name: str, payload: object) -> Path:
    domain = catalog / name
    domain.mkdir(parents=True, exist_ok=True)
    path = domain / "domain.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    assert read_domain_meta(tmp_path, "absent") == DomainMeta()


def test_read_full_payload(tmp_path: Path) -> None:
    _write_meta(
        tmp_path,
        "python-backend",
        {
            "name": "python-backend",
            "description": "FastAPI + async SQLAlchemy",
            "depends": ["@python"],
            "requires": {"npm": ["@playwright/mcp"]},
        },
    )
    meta = read_domain_meta(tmp_path, "python-backend")
    assert meta.name == "python-backend"
    assert meta.description == "FastAPI + async SQLAlchemy"
    assert meta.depends == ["@python"]
    assert meta.requires == {"npm": ["@playwright/mcp"]}


def test_read_partial_payload(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"name": "x"})
    meta = read_domain_meta(tmp_path, "x")
    assert meta.name == "x"
    assert meta.description is None
    assert meta.depends == []
    assert meta.requires == {}


def test_read_invalid_json_raises(tmp_path: Path) -> None:
    domain = tmp_path / "broken"
    domain.mkdir()
    (domain / "domain.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "broken")


def test_read_root_not_object_raises(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", [1, 2, 3])
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")


def test_read_depends_wrong_type_raises(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"name": "x", "depends": "not-a-list"})
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")


def test_read_depends_with_non_string_entry_raises(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"depends": [1, 2]})
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")


def test_read_requires_wrong_type_raises(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"requires": "npm"})
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")


def test_read_requires_inner_wrong_type_raises(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"requires": {"npm": "single-string"}})
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")


def test_read_name_must_be_string(tmp_path: Path) -> None:
    _write_meta(tmp_path, "x", {"name": 42})
    with pytest.raises(ConfigError):
        read_domain_meta(tmp_path, "x")
