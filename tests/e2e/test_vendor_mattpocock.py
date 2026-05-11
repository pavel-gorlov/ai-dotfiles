"""End-to-end tests for the ``mattpocock`` vendor.

Same shape as ``test_vendor_tonsofskills.py`` — _repo_cache is
mocked, fake SKILL.md layouts live on ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.mattpocock import MATTPOCOCK, SearchResult


def _make_skill(
    root: Path,
    *,
    category: str,
    name: str,
    description: str = "",
    tags: str = "",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Build ``<root>/skills/<category>/<name>/SKILL.md``."""
    skill_dir = root / "skills" / category / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}"]
    if description:
        lines.append(f"description: {description}")
    if tags:
        lines.append(f"tags: [{tags}]")
    lines += ["---", "", "body"]
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    if extra_files:
        for fname, body in extra_files.items():
            (skill_dir / fname).write_text(body, encoding="utf-8")
    return skill_dir


def _patch_refresh_to(
    monkeypatch: pytest.MonkeyPatch, *, cache_root: Path
) -> list[bool]:
    calls: list[bool] = []

    def fake_refresh(**kwargs: object) -> Path:
        calls.append(bool(kwargs.get("force", False)))
        return cache_root

    monkeypatch.setattr(
        "ai_dotfiles.vendors.mattpocock._repo_cache.refresh", fake_refresh
    )
    return calls


# ── list_source / metadata ──


def test_list_source_returns_source() -> None:
    assert list(MATTPOCOCK.list_source("bar")) == ["bar"]


def test_vendor_metadata() -> None:
    assert MATTPOCOCK.name == "mattpocock"
    assert MATTPOCOCK.display_name == "mattpocock"
    assert "mattpocock" in MATTPOCOCK.description
    assert isinstance(MATTPOCOCK, Vendor)


def test_vendor_deps() -> None:
    names = [d.name for d in MATTPOCOCK.deps]
    assert names == ["git"]
    assert MATTPOCOCK.deps[0].install_url == "https://git-scm.com/"


def test_deps_is_installed_reflects_shutil_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.mattpocock.shutil.which",
        lambda _name: "/usr/bin/git",
    )
    assert MATTPOCOCK.deps[0].is_installed() is True
    monkeypatch.setattr(
        "ai_dotfiles.vendors.mattpocock.shutil.which", lambda _name: None
    )
    assert MATTPOCOCK.deps[0].is_installed() is False


def test_registry_membership() -> None:
    from ai_dotfiles.vendors import REGISTRY

    assert "mattpocock" in REGISTRY
    assert REGISTRY["mattpocock"].name == "mattpocock"


# ── refresh ──


def test_refresh_delegates_to_repo_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    path = MATTPOCOCK.refresh(force=True)
    assert path == tmp_path
    assert calls == [True]


# ── search ──


def test_search_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        MATTPOCOCK.search("")
    with pytest.raises(ValueError):
        MATTPOCOCK.search("   ")


def test_search_matches_name_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(
        tmp_path,
        category="engineering",
        name="tdd",
        description="Test-driven development.",
    )
    _make_skill(
        tmp_path,
        category="engineering",
        name="diagnose",
        description="Diagnose tricky bugs.",
    )
    _make_skill(
        tmp_path,
        category="productivity",
        name="handoff",
        description="Test handoff between sessions.",
    )

    results = MATTPOCOCK.search("test")
    names = {r.name for r in results}
    assert names == {"tdd", "handoff"}
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.source == "mattpocock"
        assert r.url.startswith(
            "https://github.com/mattpocock/skills/tree/main/skills/"
        )


def test_search_matches_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, category="engineering", name="one", tags="api, db")
    _make_skill(tmp_path, category="productivity", name="two", tags="frontend")

    results = MATTPOCOCK.search("db")
    assert [r.name for r in results] == ["one"]


def test_search_empty_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, category="engineering", name="hello", description="greet")

    with pytest.raises(ExternalError) as excinfo:
        MATTPOCOCK.search("xxxnothing")
    assert "no results" in str(excinfo.value).lower()


# ── fetch ──


def test_fetch_copies_skill_into_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        category="engineering",
        name="tdd",
        description="Test-driven development.",
    )
    workdir = tmp_path / "work"
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = MATTPOCOCK.fetch("tdd", select=None, workdir=workdir)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "skill"
    assert item.name == "tdd"
    assert item.origin == "mattpocock:tdd"
    assert item.source_dir == workdir / "out" / "tdd"
    assert (item.source_dir / "SKILL.md").is_file()


def test_fetch_with_select_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ElementError) as excinfo:
        MATTPOCOCK.fetch("x", select=("a", "b"), workdir=tmp_path)
    assert "--select" in str(excinfo.value)


def test_fetch_unknown_source_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, category="engineering", name="other", description="x")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ExternalError) as excinfo:
        MATTPOCOCK.fetch("missing", select=None, workdir=tmp_path / "work")
    assert "missing" in str(excinfo.value)


def test_fetch_ambiguous_name_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, category="engineering", name="dup", description="one")
    _make_skill(cache, category="productivity", name="dup", description="two")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ElementError) as excinfo:
        MATTPOCOCK.fetch("dup", select=None, workdir=tmp_path / "work")
    assert "ambiguous" in str(excinfo.value).lower()


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        category="engineering",
        name="licensed",
        description="x",
        extra_files={"LICENSE.md": "MIT License\n"},
    )
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = MATTPOCOCK.fetch("licensed", select=None, workdir=tmp_path / "work")
    assert items[0].license == "MIT License"
