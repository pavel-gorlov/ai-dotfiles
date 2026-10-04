"""DSH scope layouts and explicit native skill-provider bindings."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core import paths
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_targets import (
    DSH_AGENT_INSTRUCTIONS_PACKAGE,
    DSH_CUSTOM_SKILL_DIRS_FIELD,
    DSH_SKILL_FILESYSTEM_PACKAGE,
    global_target_plan,
    project_target_plan,
)


def _assert_owned_paths(layout: DshLayout, base: Path) -> None:
    owned = base / "ai-dotfiles"
    assert layout.dsh_dir == base
    assert layout.skills_dir == base / "skills"
    assert layout.owned_dir == owned
    assert layout.owned_roots == (base / "skills", owned)
    assert layout.config_path == owned / "config.json"
    assert layout.patch_path == owned / "patch.json"
    assert layout.hooks_path == owned / "hooks.json"
    assert layout.bridge_path == owned / "bridge.mjs"
    assert layout.resources_dir == owned / "resources"
    assert layout.provenance_path == owned / "provenance.json"
    assert layout.local_registry_path == owned / "local.json"
    assert layout.root_agents_md not in layout.owned_roots


def test_project_layout_uses_manifest_tree_and_shared_instructions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "missing-project"
    layout = project_layout(root)
    _assert_owned_paths(layout, root / ".dsh")
    assert layout.root_agents_md == root / "AGENTS.md"
    assert layout.project_root == root
    assert list(tmp_path.iterdir()) == []


def test_global_layout_uses_native_home_without_creating_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "missing-home"
    monkeypatch.setenv("DSH_HOME", str(home))
    layout = global_layout()
    _assert_owned_paths(layout, home)
    assert layout.root_agents_md == home / "AGENTS.md"
    assert layout.project_root is None
    assert list(tmp_path.iterdir()) == []


def test_global_layout_explicit_home_wins_over_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured"
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "environment"))
    assert global_layout(configured).dsh_dir == configured


@pytest.mark.parametrize("worktree", [False, True])
def test_plan_at_git_root_needs_no_custom_binding(
    worktree: bool, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    child = root / "src"
    child.mkdir(parents=True)
    if worktree:
        (root / ".git").write_text("gitdir: /unused/worktree\n", encoding="utf-8")
    else:
        (root / ".git").mkdir()
    plan = project_target_plan(root, child)
    assert plan.layout.project_root == root
    assert plan.cwd == child
    assert plan.native_project_root == root
    assert plan.custom_skill_dirs == ()
    assert plan.skill_provider_config() == {}
    assert not (root / ".dsh").exists()


def test_nested_manifest_plan_binds_its_actual_skill_directory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    manifest_root = repository / "packages" / "app"
    cwd = manifest_root / "src"
    cwd.mkdir(parents=True)
    (repository / ".git").mkdir()
    (manifest_root / "ai-dotfiles.json").write_text("{}", encoding="utf-8")
    plan = project_target_plan(manifest_root, cwd)
    skill_dir = manifest_root / ".dsh" / "skills"
    assert plan.layout.project_root == manifest_root
    assert plan.layout.root_agents_md == manifest_root / "AGENTS.md"
    assert plan.native_project_root == repository
    assert plan.cwd == cwd
    assert plan.custom_skill_dirs == (skill_dir,)
    assert plan.skill_provider_config() == {"customSkillDirs": [str(skill_dir)]}
    assert paths.find_project_root(cwd) == manifest_root.resolve()
    assert not (repository / ".dsh").exists()
    assert not skill_dir.exists()


def test_closer_nested_git_root_does_not_move_manifest_outputs(tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested_git = root / "vendor"
    cwd = nested_git / "src"
    cwd.mkdir(parents=True)
    (root / ".git").mkdir()
    (nested_git / ".git").mkdir()
    plan = project_target_plan(root, cwd)
    assert plan.layout.skills_dir == root / ".dsh" / "skills"
    assert plan.native_project_root == nested_git
    assert plan.custom_skill_dirs == (root / ".dsh" / "skills",)


@pytest.mark.parametrize("child_cwd", [False, True])
def test_non_git_plan_distinguishes_manifest_and_native_cwd(
    child_cwd: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    cwd = root / "src" if child_cwd else root
    cwd.mkdir(parents=True)
    monkeypatch.setattr(Path, "exists", lambda _: False)
    plan = project_target_plan(root, cwd)
    assert plan.native_project_root == cwd
    assert plan.layout.project_root == root
    expected = (root / ".dsh" / "skills",) if child_cwd else ()
    assert plan.custom_skill_dirs == expected


def test_default_project_cwd_is_manifest_root(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    plan = project_target_plan(tmp_path)
    assert plan.cwd == tmp_path
    assert plan.native_project_root == tmp_path


def test_project_plan_normalizes_relative_paths_lexically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    plan = project_target_plan(Path("package/../package"), Path("package/src"))
    assert plan.layout.project_root == tmp_path / "package"
    assert plan.cwd == tmp_path / "package" / "src"
    assert plan.skill_provider_config() == {
        "customSkillDirs": [str(tmp_path / "package" / ".dsh" / "skills")]
    }


def test_global_plan_never_requires_cwd_or_project_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("DSH_HOME", str(home))

    def unexpected_discovery(start: Path | None = None) -> Path:
        raise AssertionError("global planning must not discover project roots")

    def unexpected_cwd() -> Path:
        raise AssertionError("absolute global home must not require a cwd")

    monkeypatch.setattr(paths, "find_dsh_project_root", unexpected_discovery)
    monkeypatch.setattr(paths, "current_dir", unexpected_cwd)
    plan = global_target_plan()
    assert plan.layout.project_root is None
    assert plan.layout.dsh_dir == home
    assert plan.cwd is None
    assert plan.native_project_root is None
    assert plan.custom_skill_dirs == ()
    assert plan.skill_provider_config() == {}
    assert list(tmp_path.iterdir()) == []


def test_planning_preserves_shared_global_files_and_foreign_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    files = {
        "AGENTS.md": "User instructions\n",
        "cordis.patch.yml": "User home patches\n",
        "package.json": "User package manifest\n",
        "profiles/custom/package.json": "User profile manifest\n",
        "profiles/custom/cordis.patch.yml": "User profile patches\n",
        "skills/foreign/SKILL.md": "User skill\n",
        "ai-dotfiles/foreign.txt": "Unowned collision\n",
    }
    for relative, content in files.items():
        file = home / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    before = {
        path.relative_to(home): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("DSH_HOME", str(home))
    plan = global_target_plan()
    _assert_owned_paths(plan.layout, home)
    plan.skill_provider_config()
    after = {
        path.relative_to(home): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }
    assert after == before
    for protected in ("cordis.patch.yml", "package.json", "profiles"):
        path = home / protected
        assert all(
            path != root and root not in path.parents
            for root in plan.layout.owned_roots
        )


def test_native_package_and_field_contracts() -> None:
    assert DSH_SKILL_FILESYSTEM_PACKAGE == "@deepseek-ai/dsh-skill-filesystem"
    assert DSH_AGENT_INSTRUCTIONS_PACKAGE == "@deepseek-ai/dsh-agent-instructions"
    assert DSH_CUSTOM_SKILL_DIRS_FIELD == "customSkillDirs"
