"""End-to-end tests for the ``buildwithclaude`` vendor.

The cache layer (``_repo_cache.refresh``) is monkeypatched to return a
pre-built fake cache directory on ``tmp_path``; no real git ops run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ElementError, ExternalError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.buildwithclaude import BUILDWITHCLAUDE, SearchResult


def _make_skill(
    root: Path,
    *,
    plugin: str,
    name: str,
    description: str = "",
    tags: str = "",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Build ``<root>/plugins/<plugin>/skills/<name>/SKILL.md`` with frontmatter."""
    skill_dir = root / "plugins" / plugin / "skills" / name
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
    """Stub ``_repo_cache.refresh`` so it returns ``cache_root`` directly.

    Returns a list recording every ``force=`` value passed so tests can
    assert the refresh contract.
    """
    calls: list[bool] = []

    def fake_refresh(**kwargs: object) -> Path:
        calls.append(bool(kwargs.get("force", False)))
        return cache_root

    monkeypatch.setattr(
        "ai_dotfiles.vendors.buildwithclaude._repo_cache.refresh", fake_refresh
    )
    return calls


# ── list_source / metadata ──


def test_list_source_returns_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """``list_source`` is single-skill and touches no I/O."""
    assert list(BUILDWITHCLAUDE.list_source("foo")) == ["foo"]


def test_vendor_metadata() -> None:
    assert BUILDWITHCLAUDE.name == "buildwithclaude"
    assert BUILDWITHCLAUDE.display_name == "buildwithclaude"
    assert "buildwithclaude" in BUILDWITHCLAUDE.description
    assert isinstance(BUILDWITHCLAUDE, Vendor)


def test_vendor_deps() -> None:
    names = [d.name for d in BUILDWITHCLAUDE.deps]
    assert names == ["git"]
    assert BUILDWITHCLAUDE.deps[0].install_url == "https://git-scm.com/"


def test_deps_is_installed_reflects_shutil_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.buildwithclaude.shutil.which",
        lambda _name: "/usr/bin/git",
    )
    assert BUILDWITHCLAUDE.deps[0].is_installed() is True
    monkeypatch.setattr(
        "ai_dotfiles.vendors.buildwithclaude.shutil.which", lambda _name: None
    )
    assert BUILDWITHCLAUDE.deps[0].is_installed() is False


def test_registry_membership() -> None:
    from ai_dotfiles.vendors import REGISTRY

    assert "buildwithclaude" in REGISTRY
    assert REGISTRY["buildwithclaude"].name == "buildwithclaude"


# ── refresh ──


def test_refresh_delegates_to_repo_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_refresh_to(monkeypatch, cache_root=tmp_path)

    path = BUILDWITHCLAUDE.refresh(force=True)

    assert path == tmp_path
    assert calls == [True]


# ── search ──


def test_search_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        BUILDWITHCLAUDE.search("")
    with pytest.raises(ValueError):
        BUILDWITHCLAUDE.search("   ")


def test_search_matches_name_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(
        tmp_path, plugin="ts", name="typescript-linter", description="Lint TS code."
    )
    _make_skill(
        tmp_path,
        plugin="py",
        name="python-formatter",
        description="Format Python code.",
    )
    _make_skill(
        tmp_path,
        plugin="misc",
        name="code-review",
        description="Review typescript PRs.",
    )

    results = BUILDWITHCLAUDE.search("typescript")
    names = {r.name for r in results}

    assert names == {"typescript-linter", "code-review"}
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.source == "buildwithclaude"
        assert r.url.startswith(
            "https://github.com/davepoon/buildwithclaude/tree/main/plugins/"
        )


def test_search_matches_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, plugin="p1", name="one", tags="api, backend")
    _make_skill(tmp_path, plugin="p2", name="two", tags="frontend")

    results = BUILDWITHCLAUDE.search("backend")
    assert [r.name for r in results] == ["one"]


def test_search_empty_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refresh_to(monkeypatch, cache_root=tmp_path)
    _make_skill(tmp_path, plugin="p", name="hello", description="greetings")

    with pytest.raises(ExternalError) as excinfo:
        BUILDWITHCLAUDE.search("nothingmatches")
    assert "no results" in str(excinfo.value).lower()


# ── fetch ──


def test_fetch_copies_skill_into_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache, plugin="p", name="deploy-to-vercel", description="Deploy things."
    )
    workdir = tmp_path / "work"
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = BUILDWITHCLAUDE.fetch("deploy-to-vercel", select=None, workdir=workdir)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "skill"
    assert item.name == "deploy-to-vercel"
    assert item.origin == "buildwithclaude:deploy-to-vercel"
    assert item.source_dir == workdir / "out" / "deploy-to-vercel"
    assert (item.source_dir / "SKILL.md").is_file()


def test_fetch_with_select_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ElementError) as excinfo:
        BUILDWITHCLAUDE.fetch("x", select=("a", "b"), workdir=tmp_path)
    assert "--select" in str(excinfo.value)


def test_fetch_unknown_source_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, plugin="p", name="other", description="something")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ExternalError) as excinfo:
        BUILDWITHCLAUDE.fetch("missing", select=None, workdir=tmp_path / "work")
    assert "missing" in str(excinfo.value)


def test_fetch_ambiguous_name_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(cache, plugin="p1", name="dup", description="a")
    _make_skill(cache, plugin="p2", name="dup", description="b")
    _patch_refresh_to(monkeypatch, cache_root=cache)

    with pytest.raises(ElementError) as excinfo:
        BUILDWITHCLAUDE.fetch("dup", select=None, workdir=tmp_path / "work")
    assert "ambiguous" in str(excinfo.value).lower()


def test_fetch_detects_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _make_skill(
        cache,
        plugin="p",
        name="licensed",
        description="has license",
        extra_files={"LICENSE": "MIT License\n\nCopyright..."},
    )
    _patch_refresh_to(monkeypatch, cache_root=cache)

    items = BUILDWITHCLAUDE.fetch("licensed", select=None, workdir=tmp_path / "work")
    assert items[0].license == "MIT License"
