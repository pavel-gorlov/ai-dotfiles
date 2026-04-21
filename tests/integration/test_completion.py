"""Integration tests for ``ai-dotfiles completion``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.completion import (
    _MARKER_END,
    _MARKER_START,
    completion,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def home_and_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Point HOME and AI_DOTFILES_HOME at temp dirs and clear SHELL."""
    home = tmp_path / "home"
    home.mkdir()
    storage = tmp_path / ".ai-dotfiles"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.delenv("SHELL", raising=False)
    return home, storage


def test_install_bash_writes_script_and_patches_rc(
    home_and_storage: tuple[Path, Path],
) -> None:
    home, storage = home_and_storage
    (home / ".bashrc").write_text("# original\nexport FOO=bar\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(completion, ["install", "--shell", "bash"])

    assert result.exit_code == 0, result.output
    script = storage / "completions" / "ai-dotfiles.bash"
    assert script.is_file()
    assert "_ai_dotfiles_completion" in script.read_text(encoding="utf-8")

    rc = (home / ".bashrc").read_text(encoding="utf-8")
    assert "# original" in rc
    assert _MARKER_START in rc
    assert _MARKER_END in rc
    assert str(script) in rc


def test_install_is_idempotent(home_and_storage: tuple[Path, Path]) -> None:
    home, _ = home_and_storage
    (home / ".bashrc").write_text("# original\n", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(completion, ["install", "--shell", "bash"])
    runner.invoke(completion, ["install", "--shell", "bash"])

    rc = (home / ".bashrc").read_text(encoding="utf-8")
    assert rc.count(_MARKER_START) == 1
    assert rc.count(_MARKER_END) == 1


def test_install_creates_rc_if_missing(home_and_storage: tuple[Path, Path]) -> None:
    home, _ = home_and_storage
    rc = home / ".zshrc"
    assert not rc.exists()

    runner = CliRunner()
    result = runner.invoke(completion, ["install", "--shell", "zsh"])

    assert result.exit_code == 0, result.output
    assert rc.is_file()
    assert _MARKER_START in rc.read_text(encoding="utf-8")


def test_install_print_does_not_touch_filesystem(
    home_and_storage: tuple[Path, Path],
) -> None:
    home, storage = home_and_storage

    runner = CliRunner()
    result = runner.invoke(completion, ["install", "--shell", "bash", "--print"])

    assert result.exit_code == 0, result.output
    assert "_ai_dotfiles_completion" in result.output
    assert not (home / ".bashrc").exists()
    assert not (storage / "completions").exists()


def test_install_autodetects_from_shell_env(
    home_and_storage: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = home_and_storage
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")

    runner = CliRunner()
    result = runner.invoke(completion, ["install"])

    assert result.exit_code == 0, result.output
    assert (home / ".zshrc").is_file()


def test_install_errors_on_unsupported_shell(
    home_and_storage: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/fish")

    runner = CliRunner()
    result = runner.invoke(completion, ["install"])

    assert result.exit_code != 0
    assert "Unsupported shell" in result.output


def test_install_errors_when_shell_env_missing(
    home_and_storage: tuple[Path, Path],
) -> None:
    runner = CliRunner()
    result = runner.invoke(completion, ["install"])

    assert result.exit_code != 0
    assert "$SHELL" in result.output


def test_uninstall_removes_block_and_script(
    home_and_storage: tuple[Path, Path],
) -> None:
    home, storage = home_and_storage
    (home / ".bashrc").write_text("# original\n", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(completion, ["install", "--shell", "bash"])
    script = storage / "completions" / "ai-dotfiles.bash"
    assert script.is_file()

    result = runner.invoke(completion, ["uninstall", "--shell", "bash"])

    assert result.exit_code == 0, result.output
    rc = (home / ".bashrc").read_text(encoding="utf-8")
    assert _MARKER_START not in rc
    assert "# original" in rc
    assert not script.exists()


def test_uninstall_noop_when_nothing_installed(
    home_and_storage: tuple[Path, Path],
) -> None:
    home, _ = home_and_storage
    (home / ".bashrc").write_text("# original\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(completion, ["uninstall", "--shell", "bash"])

    assert result.exit_code == 0, result.output
    assert "No completion block found" in result.output
