"""Smoke tests for the top-level ``ai-dotfiles`` CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from ai_dotfiles import __version__
from ai_dotfiles.cli import cli

TOP_LEVEL_COMMANDS = [
    "add",
    "create",
    "delete",
    "domain",
    "init",
    "install",
    "list",
    "remove",
    "stack",
    "status",
    "vendor",
]

DOMAIN_SUBCOMMANDS = ["add", "create", "delete", "list", "remove"]
STACK_SUBCOMMANDS = ["add", "apply", "create", "delete", "list", "remove"]
VENDOR_SUBCOMMANDS = ["github", "installed", "list", "npx_skills", "remove"]
VENDOR_GITHUB_SUBCOMMANDS = ["deps", "install", "list"]
VENDOR_NPX_SKILLS_SUBCOMMANDS = ["deps", "install", "list"]
VENDOR_DEPS_SUBCOMMANDS = ["check", "install"]


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for name in TOP_LEVEL_COMMANDS:
        assert name in result.output, f"{name} missing from --help"


def test_help_domain() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["domain", "--help"])
    assert result.exit_code == 0
    for name in DOMAIN_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from domain --help"


def test_help_stack() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["stack", "--help"])
    assert result.exit_code == 0
    for name in STACK_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from stack --help"


def test_help_vendor() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["vendor", "--help"])
    assert result.exit_code == 0
    for name in VENDOR_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from vendor --help"


def test_help_vendor_github() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["vendor", "github", "--help"])
    assert result.exit_code == 0
    for name in VENDOR_GITHUB_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from vendor github --help"


def test_help_vendor_npx_skills() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["vendor", "npx_skills", "--help"])
    assert result.exit_code == 0
    for name in VENDOR_NPX_SKILLS_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from vendor npx_skills --help"


def test_help_vendor_github_deps() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["vendor", "github", "deps", "--help"])
    assert result.exit_code == 0
    for name in VENDOR_DEPS_SUBCOMMANDS:
        assert name in result.output, f"{name} missing from vendor github deps --help"


def test_help_vendor_npx_skills_deps() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["vendor", "npx_skills", "deps", "--help"])
    assert result.exit_code == 0
    for name in VENDOR_DEPS_SUBCOMMANDS:
        assert (
            name in result.output
        ), f"{name} missing from vendor npx_skills deps --help"


@pytest.mark.parametrize("name", TOP_LEVEL_COMMANDS)
def test_all_commands_have_help(name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [name, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


def test_init_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "-g" in result.output
    assert "--from" in result.output


def test_add_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["add", "--help"])
    assert result.exit_code == 0
    assert "-g" in result.output
    # ITEMS / PACKAGES argument should surface in usage line
    assert "PACKAGES" in result.output.upper() or "ITEMS" in result.output.upper()
