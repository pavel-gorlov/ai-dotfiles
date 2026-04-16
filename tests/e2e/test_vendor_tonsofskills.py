"""End-to-end tests for the ``tonsofskills`` vendor.

Same shape as ``test_vendor_buildwithclaude.py`` — _repo_cache is
mocked, fake SKILL.md layouts live on ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.tonsofskills import TONSOFSKILLS, SearchResult


def _make_skill(
    root: Path,
    *,
    category: str,
    plugin: str,
    name: str,
    description: str = "",
    tags: str = "",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Build ``<root>/plugins/<category>/<plugin>/skills/<name>/SKILL.md``."""
    skill_dir = root / "plugins" / category / plugin / "skills" / name
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
        "ai_dotfiles.vendors.tonsofskills._repo_cache.refresh", fake_refresh
    )
    return calls


# ── list_source / metadata ──


def test_list_source_returns_source() -> None:
    assert list(TONSOFSKILLS.list_source("bar")) == ["bar"]


def test_vendor_metadata() -> None:
    assert TONSOFSKILLS.name == "tonsofskills"
    assert TONSOFSKILLS.display_name == "tonsofskills"
    assert "tonsofskills" in TONSOFSKILLS.description
    assert isinstance(TONSOFSKILLS, Vendor)


def test_vendor_deps() -> None:
    names = [d.name for d in TONSOFSKILLS.deps]
    assert names == ["git"]
    assert TONSOFSKILLS.deps[0].install_url == "https://git-scm.com/"


def test_deps_is_installed_reflects_shutil_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.tonsofskills.shutil.which",
        lambda _name: "/usr/bin/git",
    )
    assert TONSOFSKILLS.deps[0].is_installed() is True
    monkeypatch.setattr(
        "ai_dotfiles.vendors.tonsofskills.shutil.which", lambda _name: None
    )
    assert TONSOFSKILLS.deps[0].is_installed() is False


def test_registry_membership() -> None:
    from ai_dotfiles.vendors import REGISTRY

    assert "tonsofskills" in REGISTRY
    assert REGISTRY["tonsofskills"].name == "tonsofskills"


# ── refresh ──


def test_refresh_delegates_to_repo_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    path = TONSOFSKILLS.refresh(force=True)
    assert path == tmp_path
    assert calls == [True]


# ── search ──


def test_search_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        TONSOFSKILLS.search("")
    with pytest.raises(ValueError):
        TONSOFSKILLS.search("   ")


def test_search_matches_name_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(
        tmp_path, category="db", plugin="pg", name="pg-monitor", description="Postgres."
    )
    _make_skill(
        tmp_path, category="db", plugin="my", name="my-formatter", description="MySQL."
    )
    _make_skill(
        tmp_path,
        category="ops",
        plugin="o",
        name="review",
        description="Postgres review.",
    )

    results = TONSOFSKILLS.search("postgres")
    names = {r.name for r in results}
    assert names == {"pg-monitor", "review"}
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.source == "tonsofskills"
        assert r.url.startswith(
            "https://github.com/jeremylongshore/claude-code-plugins-plus-skills/tree/main/plugins/"
        )


def test_search_matches_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, category="c1", plugin="p1", name="one", tags="api, db")
    _make_skill(tmp_path, category="c2", plugin="p2", name="two", tags="frontend")

    results = TONSOFSKILLS.search("db")
    assert [r.name for r in results] == ["one"]


def test_search_empty_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, category="c", plugin="p", name="hello", description="greet")

    with pytest.raises(ExternalError) as excinfo:
        TONSOFSKILLS.search("xxxnothing")
    assert "no results" in str(excinfo.value).lower()


# ── fetch ──


def test_fetch_copies_skill_into_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        category="db",
        plugin="pg",
        name="pg-monitor",
        description="Monitor postgres.",
    )
    workdir = tmp_path / "work"
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = TONSOFSKILLS.fetch("pg-monitor", select=None, workdir=workdir)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "skill"
    assert item.name == "pg-monitor"
    assert item.origin == "tonsofskills:pg-monitor"
    assert item.source_dir == workdir / "out" / "pg-monitor"
    assert (item.source_dir / "SKILL.md").is_file()


def test_fetch_with_select_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ElementError) as excinfo:
        TONSOFSKILLS.fetch("x", select=("a", "b"), workdir=tmp_path)
    assert "--select" in str(excinfo.value)


def test_fetch_unknown_source_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, category="c", plugin="p", name="other", description="x")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ExternalError) as excinfo:
        TONSOFSKILLS.fetch("missing", select=None, workdir=tmp_path / "work")
    assert "missing" in str(excinfo.value)


def test_fetch_ambiguous_name_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, category="c1", plugin="a", name="dup", description="one")
    _make_skill(cache, category="c2", plugin="b", name="dup", description="two")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ElementError) as excinfo:
        TONSOFSKILLS.fetch("dup", select=None, workdir=tmp_path / "work")
    assert "ambiguous" in str(excinfo.value).lower()


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        category="c",
        plugin="p",
        name="licensed",
        description="x",
        extra_files={"LICENSE.md": "Apache License 2.0\n"},
    )
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = TONSOFSKILLS.fetch("licensed", select=None, workdir=tmp_path / "work")
    assert items[0].license == "Apache License 2.0"
