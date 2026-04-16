"""Unit tests for ``ai_dotfiles.vendors._repo_cache``.

All tests mock ``subprocess.run`` so no real git invocations happen.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors import _repo_cache


def _fake_run_factory(
    *,
    captured: list[list[str]],
    returncode: int = 0,
    stderr: str = "",
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake_run(
        argv: list[str],
        *,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode, stdout="", stderr=stderr
        )

    return fake_run


def _fake_clone_side_effect(
    captured: list[list[str]],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Fake that materialises a bare ``.git/`` inside the clone target."""

    def fake_run(
        argv: list[str],
        *,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        # First positional after 'clone' is the URL; target is the next one.
        if len(argv) >= 2 and argv[1] == "clone":
            target = Path(argv[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / ".git").mkdir(exist_ok=True)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    return fake_run


# ── cache_dir ──


def test_cache_dir_under_storage_root(tmp_storage: Path) -> None:
    path = _repo_cache.cache_dir("foo")
    assert path == tmp_storage / _repo_cache.CACHE_SUBDIR / "foo"
    # No mkdir side-effect.
    assert not path.exists()


# ── is_fresh ──


def test_is_fresh_false_when_sentinel_missing(tmp_path: Path) -> None:
    assert _repo_cache.is_fresh(tmp_path) is False


def test_is_fresh_true_within_ttl(tmp_path: Path) -> None:
    sentinel = tmp_path / _repo_cache._SENTINEL
    sentinel.touch()
    assert _repo_cache.is_fresh(tmp_path, ttl_seconds=60 * 60) is True


def test_is_fresh_false_past_ttl(tmp_path: Path) -> None:
    sentinel = tmp_path / _repo_cache._SENTINEL
    sentinel.touch()
    # Backdate the mtime.
    old = time.time() - (60 * 60 * 25)
    os.utime(sentinel, (old, old))
    assert _repo_cache.is_fresh(tmp_path, ttl_seconds=60 * 60 * 24) is False


# ── refresh ──


def test_refresh_first_time_clones(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_clone_side_effect(captured),
    )

    path = _repo_cache.refresh(
        vendor_name="foo",
        repo_url="https://example.com/foo.git",
        branch="main",
    )

    assert path == tmp_storage / _repo_cache.CACHE_SUBDIR / "foo"
    assert (path / ".fetched-at").is_file()
    # Exactly one clone call.
    assert len(captured) == 1
    assert captured[0][:2] == ["git", "clone"]
    assert "--depth=1" in captured[0]
    assert "--branch" in captured[0]
    assert "main" in captured[0]
    assert captured[0][-1] == str(path)


def test_refresh_noop_when_fresh(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pre-populate cache: fake clone first.
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_clone_side_effect(captured),
    )
    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")
    assert len(captured) == 1

    # Second call should be a no-op because sentinel is fresh.
    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")
    assert len(captured) == 1  # unchanged


def test_refresh_force_always_fetches(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_clone_side_effect(captured),
    )
    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")

    # force=True triggers fetch + reset.
    _repo_cache.refresh(
        vendor_name="foo",
        repo_url="https://example.com/foo.git",
        force=True,
    )
    # Expect 3 git calls total (clone + fetch + reset).
    assert len(captured) == 3
    assert captured[1][:4] == [
        "git",
        "-C",
        str(tmp_storage / ".vendor-cache" / "foo"),
        "fetch",
    ]
    assert captured[2][:4] == [
        "git",
        "-C",
        str(tmp_storage / ".vendor-cache" / "foo"),
        "reset",
    ]


def test_refresh_stale_cache_fetches(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_clone_side_effect(captured),
    )
    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")

    # Backdate sentinel.
    sentinel = tmp_storage / ".vendor-cache" / "foo" / ".fetched-at"
    old = time.time() - (60 * 60 * 25)
    os.utime(sentinel, (old, old))

    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")
    assert len(captured) == 3  # clone + fetch + reset


def test_refresh_clone_failure_raises(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_run_factory(captured=captured, returncode=128, stderr="repo not found"),
    )

    with pytest.raises(ExternalError) as excinfo:
        _repo_cache.refresh(
            vendor_name="foo",
            repo_url="https://example.com/bad.git",
        )
    assert "repo not found" in str(excinfo.value)


def test_refresh_missing_git_binary_raises(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(
        argv: list[str],
        *,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file", "git")

    monkeypatch.setattr("ai_dotfiles.vendors._repo_cache.subprocess.run", boom)

    with pytest.raises(ExternalError) as excinfo:
        _repo_cache.refresh(
            vendor_name="foo",
            repo_url="https://example.com/foo.git",
        )
    assert "git executable not found" in str(excinfo.value)


def test_refresh_wipes_non_git_dir(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial/corrupted cache dir without .git is wiped before clone."""
    path = tmp_storage / ".vendor-cache" / "foo"
    path.mkdir(parents=True)
    (path / "junk").write_text("stale", encoding="utf-8")

    captured: list[list[str]] = []
    monkeypatch.setattr(
        "ai_dotfiles.vendors._repo_cache.subprocess.run",
        _fake_clone_side_effect(captured),
    )

    _repo_cache.refresh(vendor_name="foo", repo_url="https://example.com/foo.git")
    assert len(captured) == 1
    assert captured[0][:2] == ["git", "clone"]
    assert not (path / "junk").exists()


# ── find_skill_dirs ──


def test_find_skill_dirs_walks_tree(tmp_path: Path) -> None:
    # Layout: two skills, one nested under plugins/, one under skills/.
    (tmp_path / "plugins" / "skill-a").mkdir(parents=True)
    (tmp_path / "plugins" / "skill-a" / "SKILL.md").write_text("x")
    (tmp_path / "plugins" / "skill-a" / "references").mkdir()
    (tmp_path / "plugins" / "skill-a" / "references" / "extra.md").write_text("x")

    (tmp_path / "skills" / "skill-b").mkdir(parents=True)
    (tmp_path / "skills" / "skill-b" / "SKILL.md").write_text("x")

    (tmp_path / "README.md").write_text("top-level")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")

    found = sorted(p.name for p in _repo_cache.find_skill_dirs(tmp_path))
    assert found == ["skill-a", "skill-b"]


def test_find_skill_dirs_skips_hidden_dirs(tmp_path: Path) -> None:
    (tmp_path / ".cache" / "skill-hidden").mkdir(parents=True)
    (tmp_path / ".cache" / "skill-hidden" / "SKILL.md").write_text("x")
    (tmp_path / "visible" / "skill-good").mkdir(parents=True)
    (tmp_path / "visible" / "skill-good" / "SKILL.md").write_text("x")

    found = [p.name for p in _repo_cache.find_skill_dirs(tmp_path)]
    assert found == ["skill-good"]


# ── read_frontmatter ──


def test_read_frontmatter_parses_scalar_fields(tmp_path: Path) -> None:
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\n"
        "name: deploy-to-vercel\n"
        "description: Deploy things to Vercel.\n"
        "---\n"
        "\n"
        "body\n",
        encoding="utf-8",
    )
    meta = _repo_cache.read_frontmatter(md)
    assert meta == {
        "name": "deploy-to-vercel",
        "description": "Deploy things to Vercel.",
    }


def test_read_frontmatter_parses_list_values(tmp_path: Path) -> None:
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\n" "name: foo\n" "tags: [backend, api, infra]\n" "---\n",
        encoding="utf-8",
    )
    meta = _repo_cache.read_frontmatter(md)
    assert meta["tags"] == "backend, api, infra"


def test_read_frontmatter_strips_quotes(tmp_path: Path) -> None:
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\n" 'name: "quoted-name"\n' "description: 'single'\n" "---\n",
        encoding="utf-8",
    )
    meta = _repo_cache.read_frontmatter(md)
    assert meta == {"name": "quoted-name", "description": "single"}


def test_read_frontmatter_no_frontmatter_returns_empty(tmp_path: Path) -> None:
    md = tmp_path / "SKILL.md"
    md.write_text("# Just a markdown file\n\nNo frontmatter.\n", encoding="utf-8")
    assert _repo_cache.read_frontmatter(md) == {}


def test_read_frontmatter_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _repo_cache.read_frontmatter(tmp_path / "nope.md") == {}


def test_read_frontmatter_tolerates_malformed_lines(tmp_path: Path) -> None:
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\n"
        "name: ok\n"
        "this-line-has-no-colon\n"
        ": missing-key\n"
        "# comment line\n"
        "\n"
        "description: fine\n"
        "---\n",
        encoding="utf-8",
    )
    meta = _repo_cache.read_frontmatter(md)
    assert meta == {"name": "ok", "description": "fine"}
