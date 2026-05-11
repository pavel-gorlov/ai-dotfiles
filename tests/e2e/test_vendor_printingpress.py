"""End-to-end tests for the ``printingpress`` vendor.

Same shape as ``test_vendor_mattpocock.py``. Layout flattened:
``cli-skills/<name>/SKILL.md`` (no category level).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.printingpress import PRINTINGPRESS, SearchResult


def _make_skill(
    root: Path,
    *,
    name: str,
    description: str = "",
    tags: str = "",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Build ``<root>/cli-skills/<name>/SKILL.md``."""
    skill_dir = root / "cli-skills" / name
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
        "ai_dotfiles.vendors.printingpress._repo_cache.refresh", fake_refresh
    )
    return calls


# ── list_source / metadata ──


def test_list_source_returns_source() -> None:
    assert list(PRINTINGPRESS.list_source("bar")) == ["bar"]


def test_vendor_metadata() -> None:
    assert PRINTINGPRESS.name == "printingpress"
    assert PRINTINGPRESS.display_name == "printingpress"
    assert "printing-press" in PRINTINGPRESS.description
    assert isinstance(PRINTINGPRESS, Vendor)


def test_vendor_deps() -> None:
    names = [d.name for d in PRINTINGPRESS.deps]
    assert names == ["git"]
    assert PRINTINGPRESS.deps[0].install_url == "https://git-scm.com/"


def test_deps_is_installed_reflects_shutil_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.printingpress.shutil.which",
        lambda _name: "/usr/bin/git",
    )
    assert PRINTINGPRESS.deps[0].is_installed() is True
    monkeypatch.setattr(
        "ai_dotfiles.vendors.printingpress.shutil.which", lambda _name: None
    )
    assert PRINTINGPRESS.deps[0].is_installed() is False


def test_registry_membership() -> None:
    from ai_dotfiles.vendors import REGISTRY

    assert "printingpress" in REGISTRY
    assert REGISTRY["printingpress"].name == "printingpress"


# ── refresh ──


def test_refresh_delegates_to_repo_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    path = PRINTINGPRESS.refresh(force=True)
    assert path == tmp_path
    assert calls == [True]


# ── search ──


def test_search_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        PRINTINGPRESS.search("")
    with pytest.raises(ValueError):
        PRINTINGPRESS.search("   ")


def test_search_matches_name_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, name="pp-openalex", description="Scholarly works catalog.")
    _make_skill(tmp_path, name="pp-arxiv", description="ArXiv preprints search.")
    _make_skill(tmp_path, name="pp-figma", description="Figma file inspector.")

    results = PRINTINGPRESS.search("arxiv")
    names = {r.name for r in results}
    assert names == {"pp-arxiv"}
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.source == "printingpress"
        assert r.url.startswith(
            "https://github.com/mvanhorn/printing-press-library/tree/main/cli-skills/"
        )


def test_search_matches_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, name="pp-one", tags="api, db")
    _make_skill(tmp_path, name="pp-two", tags="frontend")

    results = PRINTINGPRESS.search("db")
    assert [r.name for r in results] == ["pp-one"]


def test_search_empty_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, name="pp-hello", description="greet")

    with pytest.raises(ExternalError) as excinfo:
        PRINTINGPRESS.search("xxxnothing")
    assert "no results" in str(excinfo.value).lower()


# ── fetch ──


def test_fetch_copies_skill_into_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, name="pp-openalex", description="Scholarly works catalog.")
    workdir = tmp_path / "work"
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = PRINTINGPRESS.fetch("pp-openalex", select=None, workdir=workdir)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "skill"
    assert item.name == "pp-openalex"
    assert item.origin == "printingpress:pp-openalex"
    assert item.source_dir == workdir / "out" / "pp-openalex"
    assert (item.source_dir / "SKILL.md").is_file()


def test_fetch_with_select_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ElementError) as excinfo:
        PRINTINGPRESS.fetch("x", select=("a", "b"), workdir=tmp_path)
    assert "--select" in str(excinfo.value)


def test_fetch_unknown_source_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, name="pp-other", description="x")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ExternalError) as excinfo:
        PRINTINGPRESS.fetch("pp-missing", select=None, workdir=tmp_path / "work")
    assert "pp-missing" in str(excinfo.value)


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        name="pp-licensed",
        description="x",
        extra_files={"LICENSE.md": "Apache License 2.0\n"},
    )
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = PRINTINGPRESS.fetch("pp-licensed", select=None, workdir=tmp_path / "work")
    assert items[0].license == "Apache License 2.0"
