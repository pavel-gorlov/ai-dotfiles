"""Partial activation is explicit at the CLI boundary, including protections."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.commands._dsh_report import print_dsh_diagnostics
from ai_dotfiles.core.dsh_render import DshDiagnostic


def _gap() -> DshDiagnostic:
    return DshDiagnostic(
        "HOOK_UNMAPPED",
        "domain",
        "@broken",
        "hooks.PreToolUse[0].hooks[0].if",
        "Native command parser ignores handler option 'if'",
    )


def test_partial_launch_warns_about_missing_protection_and_runs() -> None:
    diagnostic = _gap()
    with patch("ai_dotfiles.commands.dsh.prepare_dsh_launch") as prepare, patch(
        "ai_dotfiles.commands.dsh.execute_dsh_launch", return_value=0
    ) as execute:
        prepare.return_value.diagnostics = (diagnostic,)
        result = CliRunner().invoke(cli, ["dsh", "launch", "--profile", "web"])

    assert result.exit_code == 0, result.output
    assert prepare.call_args.kwargs["strict"] is False
    execute.assert_called_once()
    assert "SKIPPED ERROR" in result.output
    assert "@broken" in result.output
    assert "hooks.PreToolUse[0].hooks[0].if" in result.output
    assert "activation: PARTIAL" in result.output
    assert "permission restriction is not enforced" in result.output
    assert diagnostic.blocking is True


def test_managed_strict_flag_precedes_native_argv() -> None:
    with patch("ai_dotfiles.commands.dsh.prepare_dsh_launch") as prepare, patch(
        "ai_dotfiles.commands.dsh.execute_dsh_launch", return_value=0
    ):
        prepare.return_value.diagnostics = ()
        result = CliRunner().invoke(
            cli, ["dsh", "launch", "--strict", "--profile", "web", "--strict"]
        )

    assert result.exit_code == 0, result.output
    assert prepare.call_args.kwargs["strict"] is True
    assert prepare.call_args.args[0] == ("--profile", "web", "--strict")


def test_strict_preview_reports_blocker_without_partial_claim() -> None:
    runner = CliRunner()
    with runner.isolation() as (_, _, output):
        print_dsh_diagnostics((_gap(),), strict=True)
    text = output.getvalue().decode()
    assert "BLOCKER" in text
    assert "SKIPPED" not in text
    assert "PARTIAL" not in text


def _mixed_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    storage = tmp_path / "storage"
    domain = storage / "catalog" / "mixed"
    for name, description in (("broken", ""), ("healthy", "description: Healthy")):
        folder = domain / "skills" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\n{description}\n---\nBody\n", encoding="utf-8"
        )
    (storage / "global").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex"))
    monkeypatch.setenv("DSH_HOME", str(home / "dsh"))
    manifest_path = (
        storage / "global.json" if scope == "global" else project / "ai-dotfiles.json"
    )
    manifest_path.write_text(
        json.dumps({"packages": ["@mixed"], "targets": ["claude", "codex"]}),
        encoding="utf-8",
    )
    skills = home / "codex/skills" if scope == "global" else project / ".agents/skills"
    return domain, skills, manifest_path


@pytest.mark.parametrize("scope", ["project", "global"])
def test_catalog_bad_skill_isolated_and_repaired_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    domain, skills, manifest_path = _mixed_catalog(tmp_path, monkeypatch, scope)
    original_manifest = manifest_path.read_bytes()
    args = ["install", "--prune", *(["-g"] if scope == "global" else [])]
    first = CliRunner().invoke(cli, args)
    assert first.exit_code == 0, (first.output, first.exception)
    assert "SKIPPED ERROR" in first.output and "broken" in first.output
    assert "Codex installation: PARTIAL" in first.output
    assert (skills / "healthy/SKILL.md").is_file()
    assert not (skills / "broken").exists()
    assert manifest_path.read_bytes() == original_manifest

    source = domain / "skills/broken/SKILL.md"
    source.write_text("---\nname: broken\ndescription: Repaired\n---\nBody\n")
    retry = CliRunner().invoke(cli, args)
    assert retry.exit_code == 0, (retry.output, retry.exception)
    assert "SKIPPED ERROR" not in retry.output
    assert (skills / "broken/SKILL.md").is_file()
    healthy = (skills / "healthy/SKILL.md").read_bytes()
    repeat = CliRunner().invoke(cli, args)
    assert repeat.exit_code == 0, (repeat.output, repeat.exception)
    assert (skills / "healthy/SKILL.md").read_bytes() == healthy


@pytest.mark.parametrize("command", ["install", "add"])
@pytest.mark.parametrize("scope", ["project", "global"])
def test_strict_bad_skill_refuses_before_target_or_manifest_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    scope: str,
) -> None:
    _, skills, manifest_path = _mixed_catalog(tmp_path, monkeypatch, scope)
    if command == "add":
        value = json.loads(manifest_path.read_text())
        value["packages"] = []
        manifest_path.write_text(json.dumps(value))
    original = manifest_path.read_bytes()
    args = [command, "--strict", *(["-g"] if scope == "global" else [])]
    if command == "add":
        args.append("@mixed")
    result = CliRunner().invoke(cli, args)
    assert result.exit_code != 0
    assert "broken" in result.output
    assert manifest_path.read_bytes() == original
    assert not skills.exists()
    assert not (tmp_path / "project/.claude").exists()
    assert not (tmp_path / "home/.claude").exists()


def test_strict_install_defers_dependency_manifest_repair_until_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    domain, skills, manifest_path = _mixed_catalog(tmp_path, monkeypatch, "project")
    dependency = domain.parent / "skills/dependency"
    dependency.mkdir(parents=True)
    (dependency / "SKILL.md").write_text("---\nname: dependency\n---\nBody\n")
    (domain / "domain.json").write_text(json.dumps({"depends": ["skill:dependency"]}))
    original = manifest_path.read_bytes()
    result = CliRunner().invoke(cli, ["install", "--strict"])
    assert result.exit_code != 0
    assert "dependency" in result.output
    assert manifest_path.read_bytes() == original
    assert not skills.exists()


@pytest.mark.parametrize("strict", [False, True])
def test_incremental_add_cannot_replace_another_requested_skill_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, strict: bool
) -> None:
    domain, skills, manifest_path = _mixed_catalog(tmp_path, monkeypatch, "project")
    initial = CliRunner().invoke(cli, ["install"])
    assert initial.exit_code == 0, initial.output
    other = domain.parent / "other/skills/healthy"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text(
        "---\nname: healthy\ndescription: Other origin\n---\nOther body\n"
    )
    before_manifest = manifest_path.read_bytes()
    before_skill = (skills / "healthy/SKILL.md").read_bytes()
    result = CliRunner().invoke(
        cli, ["add", *(["--strict"] if strict else []), "@other"]
    )
    assert result.exit_code != 0
    assert "Conflicting requested Codex target" in result.output
    assert manifest_path.read_bytes() == before_manifest
    assert (skills / "healthy/SKILL.md").read_bytes() == before_skill


@pytest.mark.parametrize("scope", ["project", "global"])
def test_reconcile_skips_bad_catalog_source_and_reports_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    _, skills, _ = _mixed_catalog(tmp_path, monkeypatch, scope)
    result = CliRunner().invoke(
        cli, ["reconcile", *(["-g"] if scope == "global" else [])]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "SKIPPED ERROR" in result.output
    assert "Codex reconciliation: PARTIAL" in result.output
    assert (skills / "healthy/SKILL.md").is_file()
    assert not (skills / "broken").exists()


@pytest.mark.parametrize("scope", ["project", "global"])
def test_dsh_hook_and_skill_errors_do_not_abort_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    domain, skills, manifest_path = _mixed_catalog(tmp_path, monkeypatch, scope)
    data = json.loads(manifest_path.read_text())
    data["targets"].append("dsh")
    manifest_path.write_text(json.dumps(data))
    (domain / "settings.fragment.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "true",
                                    "if": "Bash(git:*)",
                                },
                                {"type": "command", "command": "true"},
                            ],
                        }
                    ]
                }
            }
        )
    )
    result = CliRunner().invoke(
        cli, ["install", *(["-g"] if scope == "global" else [])]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "SKIPPED ERROR" in result.output
    assert "DSH activation: PARTIAL" in result.output
    assert "hook or permission restriction is not enforced" in result.output
    assert (skills / "healthy/SKILL.md").is_file()
    dsh_root = tmp_path / "home/dsh" if scope == "global" else tmp_path / "project/.dsh"
    assert (dsh_root / "skills/healthy/SKILL.md").is_file()
    assert not (dsh_root / "skills/broken").exists()
    hooks = json.loads((dsh_root / "ai-dotfiles/hooks.json").read_text())
    native_handlers = hooks["hooks"]["PreToolUse"][0]["hooks"]
    assert native_handlers == [{"type": "command", "command": "true"}]
    raw = hooks["aiDotfiles"]["sources"][0]["value"]
    assert raw["hooks"]["PreToolUse"][0]["hooks"][0]["if"] == "Bash(git:*)"


@pytest.mark.parametrize("strict", [False, True])
def test_dsh_migration_preview_distinguishes_partial_and_strict_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, strict: bool
) -> None:
    _mixed_catalog(tmp_path, monkeypatch, "project")
    claude = tmp_path / "project/.claude"
    claude.mkdir()
    original = json.dumps(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "true", "if": "Bash(git:*)"},
                            {"type": "command", "command": "true"},
                        ],
                    }
                ]
            }
        }
    ).encode()
    settings = claude / "settings.json"
    settings.write_bytes(original)
    result = CliRunner().invoke(
        cli, ["migrate", "--to", "dsh", "--dry-run", *(["--strict"] if strict else [])]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert ("Activation: BLOCKED" if strict else "Activation: PARTIAL") in result.output
    assert ("BLOCKER" if strict else "SKIPPED ERROR") in result.output
    assert settings.read_bytes() == original
    assert not (tmp_path / "project/.dsh").exists()
