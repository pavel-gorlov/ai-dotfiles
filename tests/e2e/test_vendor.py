"""End-to-end tests for ``ai-dotfiles vendor``."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.vendor import vendor


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def storage(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_dir = home / ".ai-dotfiles"
    storage_dir.mkdir()
    (storage_dir / "catalog").mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    return storage_dir


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _catalog(storage: Path) -> Path:
    return storage / "catalog"


def _make_fake_checkout(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, str] | None = None,
    as_skill: bool = True,
) -> None:
    """Patch ``git_sparse_checkout`` to create a fake local tree at ``dest``.

    - ``as_skill=True`` creates a directory with ``SKILL.md`` inside.
    - Otherwise it creates a directory without SKILL.md (defaulting to skill kind).
    """

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        dest.mkdir(parents=True, exist_ok=False)
        if as_skill:
            (dest / "SKILL.md").write_text("# fake skill\n", encoding="utf-8")
        if payload:
            for name, body in payload.items():
                (dest / name).write_text(body, encoding="utf-8")

    monkeypatch.setattr(
        "ai_dotfiles.commands.vendor.git_ops.git_sparse_checkout",
        fake_checkout,
    )


def test_vendor_github_tree(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url])
    assert result.exit_code == 0, result.output

    dest = _catalog(storage) / "skills" / "frontend-design"
    assert dest.is_dir()
    assert (dest / "SKILL.md").is_file()
    assert "Downloaded to catalog/skills/frontend-design/" in result.output


def test_vendor_creates_source_file(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url])
    assert result.exit_code == 0, result.output

    source = _catalog(storage) / "skills" / "frontend-design" / ".source"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    assert "origin: github:acme/tools/skills/frontend-design" in text
    assert "tool: ai-dotfiles vendor" in text
    assert "license: unknown" in text


def test_vendor_destination_exists(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    existing = _catalog(storage) / "skills" / "frontend-design"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("already here", encoding="utf-8")

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url])
    assert result.exit_code != 0
    assert "already exists" in result.output
    # Original content preserved.
    assert (existing / "SKILL.md").read_text() == "already here"


def test_vendor_force_overwrites(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    existing = _catalog(storage) / "skills" / "frontend-design"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("already here", encoding="utf-8")

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url, "--force"])
    assert result.exit_code == 0, result.output
    assert (existing / "SKILL.md").read_text().startswith("# fake skill")


def test_vendor_invalid_url(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(vendor, ["https://gitlab.com/x/y"])
    assert result.exit_code != 0
    assert "Unrecognized GitHub URL" in result.output
    assert "https://github.com" in result.output


def test_vendor_print_next_steps(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url])
    assert result.exit_code == 0, result.output
    assert "Ready to use:" in result.output
    assert "ai-dotfiles add skill:frontend-design" in result.output


def test_vendor_source_file_format(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_fake_checkout(monkeypatch)
    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, [url])
    assert result.exit_code == 0, result.output

    source = _catalog(storage) / "skills" / "frontend-design" / ".source"
    lines = source.read_text(encoding="utf-8").splitlines()

    # Key-value, one per line (not JSON).
    assert not source.read_text().lstrip().startswith("{")
    kv: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        kv[key.strip()] = value.strip()

    assert kv["origin"] == "github:acme/tools/skills/frontend-design"
    assert kv["fetched"] == date.today().isoformat()
    assert kv["tool"] == "ai-dotfiles vendor"
    assert kv["license"] == "unknown"


def test_vendor_ssh_url_clones_repo_root(
    runner: CliRunner, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSH URL with no subpath should clone to catalog/skills/<repo>/."""
    captured: dict[str, Any] = {}

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        captured["repo_url"] = repo_url
        captured["subpath"] = subpath
        captured["branch"] = branch
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    monkeypatch.setattr(
        "ai_dotfiles.commands.vendor.git_ops.git_sparse_checkout",
        fake_checkout,
    )

    result = runner.invoke(vendor, ["git@github.com:acme/tools.git"])
    assert result.exit_code == 0, result.output

    dest = _catalog(storage) / "skills" / "tools"
    assert dest.is_dir()
    assert captured["subpath"] == ""
    # .source should record just the owner/repo origin (no subpath).
    text = (dest / ".source").read_text(encoding="utf-8")
    assert "origin: github:acme/tools\n" in text
