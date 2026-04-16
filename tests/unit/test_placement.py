"""Unit tests for ai_dotfiles.vendors.placement."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.vendors import source_file
from ai_dotfiles.vendors.base import FetchedItem
from ai_dotfiles.vendors.placement import place_item


def _make_staged_skill(
    tmp_path: Path,
    *,
    name: str = "my-skill",
    kind: Literal["skill", "agent", "rule"] = "skill",
    origin: str = "github:acme/tools/skills/my-skill",
    license: str | None = "MIT",
) -> FetchedItem:
    staged = tmp_path / f"staging-{name}"
    staged.mkdir()
    (staged / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    return FetchedItem(
        kind=kind,
        name=name,
        source_dir=staged,
        origin=origin,
        license=license,
    )


# ── happy path ─────────────────────────────────────────────────────────────


def test_place_item_moves_dir_and_writes_source(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(tmp_path)

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    assert final == catalog / "skills" / "my-skill"
    assert final.is_dir()
    assert (final / "SKILL.md").is_file()
    assert (final / ".source").is_file()
    assert not item.source_dir.exists(), "source_dir should have been moved"


def test_place_item_source_file_contents(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(
        tmp_path,
        origin="github:acme/tools/skills/my-skill",
        license="Apache-2.0",
    )

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    meta = source_file.read(final)
    assert meta is not None
    assert meta.vendor == "github"
    assert meta.origin == "github:acme/tools/skills/my-skill"
    assert meta.tool == "ai-dotfiles vendor"
    assert meta.license == "Apache-2.0"


def test_place_item_license_none_written_as_unknown(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(tmp_path, license=None)

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    meta = source_file.read(final)
    assert meta is not None
    assert meta.license == "unknown"


def test_place_item_creates_parent_dirs(tmp_path: Path) -> None:
    catalog = tmp_path / "nested" / "catalog"
    assert not catalog.exists()
    item = _make_staged_skill(tmp_path)

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    assert final.parent == catalog / "skills"
    assert final.parent.is_dir()


# ── kind routing ───────────────────────────────────────────────────────────


def test_place_item_agent_uses_agents_subdir(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(tmp_path, name="reviewer", kind="agent")

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    assert final == catalog / "agents" / "reviewer"


def test_place_item_rule_uses_rules_subdir(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(tmp_path, name="style", kind="rule")

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    assert final == catalog / "rules" / "style"


# ── conflicts ──────────────────────────────────────────────────────────────


def test_place_item_existing_destination_without_force_raises(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    (catalog / "skills" / "my-skill").mkdir(parents=True)
    (catalog / "skills" / "my-skill" / "existing.md").write_text("x", encoding="utf-8")
    item = _make_staged_skill(tmp_path)

    with pytest.raises(ElementError, match="--force"):
        place_item(item, catalog_root=catalog, force=False, vendor_name="github")

    # Staging should remain untouched so caller can decide what to do.
    assert item.source_dir.exists()


def test_place_item_existing_destination_with_force_overwrites(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    dest = catalog / "skills" / "my-skill"
    dest.mkdir(parents=True)
    (dest / "existing.md").write_text("old", encoding="utf-8")
    item = _make_staged_skill(tmp_path)

    final = place_item(item, catalog_root=catalog, force=True, vendor_name="github")

    assert final == dest
    assert not (dest / "existing.md").exists()
    assert (dest / "SKILL.md").is_file()
    assert (dest / ".source").is_file()


# ── error propagation ─────────────────────────────────────────────────────


def test_place_item_missing_source_dir_propagates(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    missing = tmp_path / "nowhere"
    item = FetchedItem(
        kind="skill",
        name="ghost",
        source_dir=missing,
        origin="github:a/b",
        license=None,
    )

    with pytest.raises(FileNotFoundError):
        place_item(item, catalog_root=catalog, force=False, vendor_name="github")


def test_place_item_vendor_name_recorded(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    item = _make_staged_skill(tmp_path)

    final = place_item(item, catalog_root=catalog, force=False, vendor_name="skills_sh")

    meta = source_file.read(final)
    assert meta is not None
    assert meta.vendor == "skills_sh"
