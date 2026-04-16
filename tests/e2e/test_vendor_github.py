"""End-to-end tests for the GitHub vendor (``vendors/github.py``).

Drive the vendor via the :class:`~ai_dotfiles.vendors.base.Vendor`
protocol directly — V4 is what rewires the CLI, so these tests
deliberately do not go through ``click``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.vendors.base import Vendor
from ai_dotfiles.vendors.github import GITHUB


def _fake_sparse_checkout_factory(
    *,
    payload: dict[str, str] | None = None,
    as_skill: bool = True,
    license_text: str | None = None,
    license_filename: str = "LICENSE",
    captured: dict[str, Any] | None = None,
) -> Any:
    """Build a ``git_sparse_checkout`` replacement that lays out a fake tree."""

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        if captured is not None:
            captured["repo_url"] = repo_url
            captured["subpath"] = subpath
            captured["branch"] = branch
            captured["dest"] = dest
        dest.mkdir(parents=True, exist_ok=False)
        if as_skill:
            (dest / "SKILL.md").write_text("# fake skill\n", encoding="utf-8")
        if payload:
            for name, body in payload.items():
                (dest / name).write_text(body, encoding="utf-8")
        if license_text is not None:
            (dest / license_filename).write_text(license_text, encoding="utf-8")

    return fake_checkout


def test_fetch_tree_url_produces_single_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``/tree/<branch>/<subpath>`` URL fetches one skill item."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(captured=captured),
    )

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    items = GITHUB.fetch(url, select=None, workdir=tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "skill"
    assert item.name == "frontend-design"
    assert item.origin == "github:acme/tools/skills/frontend-design"
    assert item.source_dir.is_dir()
    assert (item.source_dir / "SKILL.md").is_file()
    assert item.license is None

    # The sparse checkout was invoked with the expected args.
    assert captured["repo_url"] == "https://github.com/acme/tools.git"
    assert captured["subpath"] == "skills/frontend-design"
    assert captured["branch"] == "main"


def test_fetch_root_url_no_subpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root URL produces ``origin='github:org/repo'`` with no subpath."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(captured=captured),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools",
        select=None,
        workdir=tmp_path,
    )

    assert len(items) == 1
    item = items[0]
    assert item.name == "tools"
    assert item.origin == "github:acme/tools"
    assert captured["subpath"] == ""


def test_fetch_ssh_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SSH URL form is parsed and fetched like a root URL."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(captured=captured),
    )

    items = GITHUB.fetch(
        "git@github.com:acme/tools.git",
        select=None,
        workdir=tmp_path,
    )

    assert len(items) == 1
    assert items[0].origin == "github:acme/tools"
    assert captured["repo_url"] == "git@github.com:acme/tools.git"
    assert captured["subpath"] == ""


def test_fetch_invalid_url_raises_element_error(tmp_path: Path) -> None:
    with pytest.raises(ElementError) as excinfo:
        GITHUB.fetch("https://gitlab.com/x/y", select=None, workdir=tmp_path)
    assert "Unrecognized GitHub URL" in str(excinfo.value)


def test_fetch_with_select_raises_element_error(tmp_path: Path) -> None:
    with pytest.raises(ElementError) as excinfo:
        GITHUB.fetch(
            "https://github.com/acme/tools",
            select=("something",),
            workdir=tmp_path,
        )
    assert "does not support --select" in str(excinfo.value)


def test_fetch_detects_license_from_license_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First non-blank line of ``LICENSE`` becomes ``item.license``."""
    license_body = "\n\nMIT License\n\nCopyright (c) 2024 Acme\n"
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(license_text=license_body),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools/tree/main/skills/frontend-design",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].license == "MIT License"


def test_fetch_license_truncated_to_60_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_line = "X" * 200
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(license_text=long_line),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].license is not None
    assert len(items[0].license) == 60
    assert items[0].license == "X" * 60


def test_fetch_license_license_md_also_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(
            license_text="Apache License 2.0", license_filename="LICENSE.md"
        ),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].license == "Apache License 2.0"


def test_fetch_no_license_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].license is None


def test_fetch_empty_license_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A LICENSE file with only blank lines yields ``None``."""
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(license_text="\n\n   \n"),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].license is None


def test_fetch_kind_defaults_to_skill_when_undetected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory without SKILL.md (and no other hints) defaults to skill."""
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(as_skill=False, payload={"README.md": "# hi\n"}),
    )

    items = GITHUB.fetch(
        "https://github.com/acme/tools/tree/main/some/path",
        select=None,
        workdir=tmp_path,
    )

    assert items[0].kind == "skill"


def test_fetch_overwrites_prior_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prior staging directory at the same name is cleared before fetch."""
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        _fake_sparse_checkout_factory(),
    )

    stale = tmp_path / "frontend-design"
    stale.mkdir()
    (stale / "stale.txt").write_text("old", encoding="utf-8")

    items = GITHUB.fetch(
        "https://github.com/acme/tools/tree/main/skills/frontend-design",
        select=None,
        workdir=tmp_path,
    )

    assert not (items[0].source_dir / "stale.txt").exists()
    assert (items[0].source_dir / "SKILL.md").is_file()


def test_list_source_returns_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``list_source`` returns the names at the first level of the sparse tree."""

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "alpha").mkdir()
        (dest / "beta").mkdir()
        (dest / "gamma.md").write_text("# g\n", encoding="utf-8")

    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        fake_checkout,
    )

    entries = list(GITHUB.list_source("https://github.com/acme/tools/tree/main/skills"))
    assert entries == ["alpha", "beta", "gamma.md"]


def test_list_source_root_url_uses_git_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For a root URL (no subpath), ``list_source`` uses ``git_clone``."""
    called: dict[str, Any] = {}

    def fake_clone(url: str, dest: Path, branch: str | None = None) -> None:
        called["url"] = url
        called["branch"] = branch
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "one").mkdir()
        (dest / "two.md").write_text("x", encoding="utf-8")

    def fake_sparse(
        repo_url: str, subpath: str, dest: Path, branch: str | None = None
    ) -> None:
        called["sparse_called"] = True

    monkeypatch.setattr("ai_dotfiles.vendors.github.git_ops.git_clone", fake_clone)
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout", fake_sparse
    )

    entries = list(GITHUB.list_source("https://github.com/acme/tools"))
    assert entries == ["one", "two.md"]
    assert called.get("url") == "https://github.com/acme/tools.git"
    assert called.get("branch") == "main"
    assert "sparse_called" not in called


def test_list_source_invalid_url_raises(tmp_path: Path) -> None:
    with pytest.raises(ElementError):
        list(GITHUB.list_source("https://gitlab.com/x/y"))


def test_vendor_metadata() -> None:
    """Module-level constants for the vendor."""
    assert GITHUB.name == "github"
    assert GITHUB.display_name == "GitHub"
    assert GITHUB.description == "Sparse-clone a subtree from GitHub."
    # Runtime protocol check.
    assert isinstance(GITHUB, Vendor)


def test_vendor_deps_contains_git() -> None:
    dep_names = [d.name for d in GITHUB.deps]
    assert "git" in dep_names


def test_git_dependency_is_installed_true_when_git_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.shutil.which", lambda _name: "/usr/bin/git"
    )
    git_dep = next(d for d in GITHUB.deps if d.name == "git")
    assert git_dep.is_installed() is True


def test_git_dependency_is_installed_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_dotfiles.vendors.github.shutil.which", lambda _name: None)
    git_dep = next(d for d in GITHUB.deps if d.name == "git")
    assert git_dep.is_installed() is False
