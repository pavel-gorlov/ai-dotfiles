"""Native Pi project selection, complete bundles, and lifecycle."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from ai_dotfiles.cli import cli

OWNERSHIP = Path(".pi/.ai-dotfiles-ownership.json")
SKILLS = Path(".pi/skills")


@pytest.fixture
def pi_project(
    tmp_project: Path,
    tmp_storage: Path,
    tmp_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.chdir(tmp_project)
    return tmp_project, tmp_storage / "catalog"


def invoke(*args: str, expected: int = 0) -> Result:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == expected, (result.output, result.exception)
    return result


def write_project(project: Path, targets: list[str], packages: list[str]) -> Path:
    path = project / "ai-dotfiles.json"
    data = {"packages": packages, "targets": targets, "other": {"keep": True}}
    path.write_text(" " + json.dumps(data) + "\n", encoding="utf-8")
    return path


def make_skill(source: Path, *, name: str | None = None, depends: str = "") -> Path:
    source.mkdir(parents=True)
    text = (
        f"---\nname: {name or source.name}\ndescription: Fixture skill.\n"
        f"{depends}---\n\nBody.\n"
    )
    (source / "SKILL.md").write_text(text, encoding="utf-8")
    return source


def test_pi_init_explicit_repeat_and_global_refusal(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = pi_project
    manifest = project / "ai-dotfiles.json"
    invoke("init", "-g", "--target", "pi", expected=2)
    assert not manifest.exists()
    assert not catalog.exists()
    invoke("init", "--target", "pi")
    assert (
        manifest.read_bytes()
        == b'{\n  "packages": [],\n  "targets": [\n    "pi"\n  ]\n}\n'
    )
    manifest = write_project(project, ["codex", "unknown", "pi"], [])
    previous = manifest.read_bytes()
    assert "already exists" in invoke("init", "--target", "pi").output
    assert manifest.read_bytes() == previous

    plain = project.parent / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    invoke("init")
    assert (plain / "ai-dotfiles.json").read_bytes() == b'{\n  "packages": []\n}\n'


def test_empty_pi_project_has_no_managed_tree(pi_project: tuple[Path, Path]) -> None:
    project, _ = pi_project
    invoke("init", "--target", "pi")
    invoke("install", "--prune")
    invoke("status")
    invoke("reconcile", "--check", "--strict")
    assert not (project / ".pi").exists()


def test_pi_add_install_remove_manage_complete_bundles_and_dependencies(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    manifest = write_project(project, ["future", "pi"], [])
    base = make_skill(catalog / "skills" / "base")
    domain = catalog / "suite"
    source = make_skill(domain / "skills" / "primary", name='"primary-command"')
    references = source / "references"
    references.mkdir()
    (references / "guide.md").write_text("Reference data", encoding="utf-8")
    scripts = source / "scripts"
    scripts.mkdir()
    script = scripts / "run.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    (scripts / "guide.md").symlink_to("../references/guide.md")
    (source / "docs").symlink_to("references", target_is_directory=True)
    (domain / "domain.json").write_text(
        '{"name":"suite","depends":["skill:base"]}', encoding="utf-8"
    )
    for folder, member in (("agents", "tester.md"), ("rules", "always.md")):
        (domain / folder).mkdir()
        (domain / folder / member).write_text("Unsupported by Pi", encoding="utf-8")

    added = invoke("add", "@suite")
    assert "skill:base (pulled in as a dependency)" in added.output
    assert "[SKIPPED] Pi suite/agents/tester.md" in added.output
    assert "[SKIPPED] Pi suite/rules/always.md" in added.output
    bundle = project / SKILLS / "primary"
    assert os.readlink(bundle) == str(source)
    assert (bundle / "scripts" / "run.sh").stat().st_mode & 0o777 == 0o755
    assert (bundle / "docs" / "guide.md").read_bytes() == b"Reference data"
    assert (bundle / "scripts" / "guide.md").read_bytes() == b"Reference data"
    assert (project / SKILLS / "base").resolve() == base
    assert not (project / ".claude").exists()
    assert not (project / ".agents").exists()
    assert json.loads(manifest.read_text()) == {
        "packages": ["skill:base", "@suite"],
        "targets": ["future", "pi"],
        "other": {"keep": True},
    }

    ownership = project / OWNERSHIP
    snapshot = (ownership.stat().st_ino, ownership.read_bytes(), bundle.lstat().st_ino)
    assert "already installed" in invoke("add", "@suite").output
    invoke("install", "--prune")
    assert (
        ownership.stat().st_ino,
        ownership.read_bytes(),
        bundle.lstat().st_ino,
    ) == snapshot
    assert f"{SKILLS / 'primary'} OK" in invoke("status").output
    assert "depend on them" in invoke("remove", "skill:base", expected=1).output

    private = project / ".pi" / "settings.json"
    private.write_bytes(b'{"user": true}\n')
    foreign = project / SKILLS / "foreign"
    foreign.symlink_to(catalog / "already-deleted")
    invoke("remove", "@suite", "skill:base")
    assert not bundle.is_symlink()
    assert not ownership.exists()
    assert foreign.is_symlink()
    assert private.read_bytes() == b'{"user": true}\n'
    invoke("install", "--prune")
    assert foreign.is_symlink()
    assert "None of these packages" in invoke("remove", "@suite").output
    invoke("reconcile", "--check", "--strict")


def test_pi_global_manifest_does_not_enable_native_global_writes(
    pi_project: tuple[Path, Path], tmp_claude_home: Path
) -> None:
    _, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    (catalog.parent / "global.json").write_text('{"targets":["pi"],"packages":[]}')
    invoke("add", "-g", "skill:fixture")
    invoke("install", "-g")
    invoke("status", "-g")
    invoke("reconcile", "-g", "--check")
    invoke("remove", "-g", "skill:fixture")
    assert not (tmp_claude_home / ".pi").exists()


@pytest.mark.parametrize("same_destination", [True, False], ids=["destination", "name"])
def test_pi_rejects_catalog_skill_collisions_before_mutation(
    pi_project: tuple[Path, Path], same_destination: bool
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "first")
    make_skill(
        catalog / "suite" / "skills" / ("first" if same_destination else "other"),
        name="distinct" if same_destination else '"first"',
    )
    manifest = write_project(project, ["pi", "codex"], ["skill:first"])
    before = manifest.read_bytes()
    error = invoke("add", "@suite", expected=1)
    assert (
        "destination collision" if same_destination else "name collision"
    ) in error.output
    assert manifest.read_bytes() == before
    assert not (project / ".pi").exists()
    assert not (project / ".agents").exists()


def test_pi_deduplicates_the_same_source_and_skips_standalone_rule_and_agent(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    source = make_skill(catalog / "skills" / "fixture")
    (catalog / "rules").mkdir()
    (catalog / "rules" / "policy.md").touch()
    (catalog / "agents").mkdir()
    (catalog / "agents" / "tester.md").touch()
    write_project(
        project,
        ["pi"],
        ["skill:fixture", "skill: fixture", "rule:policy", "agent:tester"],
    )
    output = invoke("install", "--strict").output
    assert "[SKIPPED] Pi rule:policy" in output
    assert "[SKIPPED] Pi agent:tester" in output
    assert list((project / SKILLS).iterdir()) == [project / SKILLS / "fixture"]
    assert (project / SKILLS / "fixture").resolve() == source


@pytest.mark.parametrize(
    "problem", ["root-link", "ancestor-link", "external", "broken", "loop", "fifo"]
)
def test_pi_rejects_unsafe_bundles(
    pi_project: tuple[Path, Path], tmp_path: Path, problem: str
) -> None:
    project, catalog = pi_project
    source = catalog / "skills" / "fixture"
    outside = make_skill(tmp_path / "outside" / "fixture")
    if problem == "ancestor-link":
        catalog.mkdir()
        (catalog / "skills").symlink_to(outside.parent, target_is_directory=True)
    elif problem == "root-link":
        source.parent.mkdir(parents=True)
        source.symlink_to(outside, target_is_directory=True)
    else:
        make_skill(source)
        extra = source / "extra"
        if problem == "fifo":
            if not hasattr(os, "mkfifo"):
                pytest.skip("mkfifo is unavailable")
            os.mkfifo(extra)
        else:
            target = {"external": outside, "broken": "missing", "loop": "extra"}[
                problem
            ]
            extra.symlink_to(target)
    manifest = write_project(project, ["pi"], [])
    before = manifest.read_bytes()
    error = invoke("add", "skill:fixture", expected=1)
    assert "Pi" in error.output
    assert manifest.read_bytes() == before
    assert not (project / ".pi").exists()


def test_pi_gitignore_covers_generated_paths_and_preserves_user_files(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    gitignore = project / ".gitignore"
    gitignore.write_text("/notes.txt\n", encoding="utf-8")
    make_skill(catalog / "suite" / "skills" / "fixture")
    (catalog / "suite" / "mcp.fragment.json").write_text(
        '{"mcpServers":{"fixture":{"command":"serve"}}}', encoding="utf-8"
    )
    write_project(project, ["pi"], [])
    user_skill = make_skill(project / SKILLS / "personal")

    invoke("add", "@suite", "--no-gitignore")
    assert gitignore.read_text() == "/notes.txt\n"
    invoke("install")
    patterns = set(gitignore.read_text().splitlines())
    assert {
        "/notes.txt",
        "/.pi/skills/fixture",
        f"/{OWNERSHIP}",
        "/.pi/mcp.json",
    } <= patterns
    assert f"/{user_skill.relative_to(project)}" not in patterns

    mcp = project / ".pi" / "mcp.json"
    config = json.loads(mcp.read_bytes())
    config["mcpServers"]["personal"] = {"command": "user-command"}
    mcp.write_text(json.dumps(config), encoding="utf-8")
    invoke("reconcile")
    assert "/.pi/mcp.json" not in gitignore.read_text().splitlines()
    invoke("remove", "@suite")
    assert gitignore.read_text() == "/notes.txt\n"
    assert json.loads(mcp.read_bytes()) == {
        "mcpServers": {"personal": {"command": "user-command"}}
    }


def test_pi_domain_member_changes_refresh_the_selected_project(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    manifest = write_project(project, ["pi"], [])
    domain = catalog / "suite"
    domain.mkdir(parents=True)
    invoke("add", "@suite")
    before = manifest.read_bytes()

    invoke("domain", "add", "suite", "skill", "fixture")
    source = domain / "skills" / "fixture"
    installed = project / SKILLS / "fixture"
    assert installed.resolve(strict=True) == source
    assert f"/{SKILLS / 'fixture'}" in (project / ".gitignore").read_text().splitlines()
    assert manifest.read_bytes() == before

    foreign = project / SKILLS / "fixture"
    foreign.unlink()
    foreign.write_bytes(b"private")
    error = invoke("domain", "remove", "suite", "skill", "fixture", expected=1)
    assert "foreign" in error.output
    assert (source / "SKILL.md").is_file()
    assert foreign.read_bytes() == b"private"

    foreign.unlink()
    invoke("reconcile")
    invoke("domain", "remove", "suite", "skill", "fixture")
    assert not source.exists()
    assert not installed.is_symlink()
    assert not (project / OWNERSHIP).exists()
    assert manifest.read_bytes() == before
    invoke("reconcile", "--check", "--strict")
