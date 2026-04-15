"""Unit tests for ai_dotfiles.core.git_ops."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.core.git_ops import (
    detect_element_type,
    git_clone,
    git_sparse_checkout,
    parse_github_url,
)

# ── parse_github_url ───────────────────────────────────────────────────────


def test_parse_github_url_tree() -> None:
    result = parse_github_url(
        "https://github.com/user/repo/tree/main/skills/frontend-design"
    )
    assert result == (
        "https://github.com/user/repo.git",
        "main",
        "skills/frontend-design",
        "frontend-design",
    )


def test_parse_github_url_tree_nested() -> None:
    result = parse_github_url(
        "https://github.com/acme/tools/tree/develop/path/to/skill"
    )
    assert result == (
        "https://github.com/acme/tools.git",
        "develop",
        "path/to/skill",
        "skill",
    )


def test_parse_github_url_root() -> None:
    result = parse_github_url("https://github.com/user/repo")
    assert result == ("https://github.com/user/repo.git", "main", "", "repo")


def test_parse_github_url_root_with_dot_git() -> None:
    result = parse_github_url("https://github.com/user/repo.git")
    assert result == ("https://github.com/user/repo.git", "main", "", "repo")


def test_parse_github_url_ssh() -> None:
    result = parse_github_url("git@github.com:user/repo.git")
    assert result == ("git@github.com:user/repo.git", "main", "", "repo")


def test_parse_github_url_ssh_no_suffix() -> None:
    result = parse_github_url("git@github.com:user/repo")
    assert result == ("git@github.com:user/repo.git", "main", "", "repo")


def test_parse_github_url_invalid() -> None:
    assert parse_github_url("https://gitlab.com/user/repo") is None
    assert parse_github_url("not a url") is None
    assert parse_github_url("") is None


# ── git_clone ──────────────────────────────────────────────────────────────


def _ok_completed(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")


def test_git_clone_success(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    with patch("ai_dotfiles.core.git_ops.subprocess.run") as run:
        run.return_value = _ok_completed(["git", "clone", "url", str(dest)])
        git_clone("https://github.com/u/r.git", dest)

    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == [
        "git",
        "clone",
        "https://github.com/u/r.git",
        str(dest),
    ]
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_git_clone_with_branch(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    with patch("ai_dotfiles.core.git_ops.subprocess.run") as run:
        run.return_value = _ok_completed([])
        git_clone("url", dest, branch="dev")

    called_args = run.call_args[0][0]
    assert called_args == ["git", "clone", "--branch", "dev", "url", str(dest)]


def test_git_clone_failure_raises_external_error(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    err = subprocess.CalledProcessError(
        returncode=128,
        cmd=["git", "clone", "url", str(dest)],
        stderr="fatal: repository not found",
    )
    with (
        patch("ai_dotfiles.core.git_ops.subprocess.run", side_effect=err),
        pytest.raises(ExternalError) as exc_info,
    ):
        git_clone("url", dest)

    msg = str(exc_info.value)
    assert "git clone" in msg
    assert "fatal: repository not found" in msg


def test_git_clone_missing_git_binary(tmp_path: Path) -> None:
    with (
        patch(
            "ai_dotfiles.core.git_ops.subprocess.run", side_effect=FileNotFoundError()
        ),
        pytest.raises(ExternalError, match="git executable not found"),
    ):
        git_clone("url", tmp_path / "out")


# ── git_sparse_checkout ────────────────────────────────────────────────────


def _fake_sparse_clone_populates(subpath: str) -> MagicMock:
    """Return a subprocess.run side effect that materializes ``subpath``.

    We cannot really clone, so when the fake sees ``git clone ...`` we create
    the destination directory and seed the expected subpath so the subsequent
    copy step succeeds.
    """

    def _side_effect(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if len(cmd) >= 2 and cmd[1] == "clone":
            dest = Path(cmd[-1])
            (dest / subpath).mkdir(parents=True, exist_ok=True)
            (dest / subpath / "SKILL.md").write_text("x", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock = MagicMock(side_effect=_side_effect)
    return mock


def test_sparse_checkout_calls(tmp_path: Path) -> None:
    dest = tmp_path / "result"
    subpath = "skills/my-skill"
    fake_run = _fake_sparse_clone_populates(subpath)

    with patch("ai_dotfiles.core.git_ops.subprocess.run", fake_run):
        git_sparse_checkout("https://github.com/u/r.git", subpath, dest, branch="main")

    # 3 git invocations: clone, sparse-checkout set, checkout
    assert fake_run.call_count == 3
    calls = [call.args[0] for call in fake_run.call_args_list]

    assert calls[0][:4] == ["git", "clone", "--filter=blob:none", "--no-checkout"]
    assert "--branch" in calls[0]
    assert calls[1][:3] == ["git", "sparse-checkout", "set"]
    assert calls[1][3] == subpath
    assert calls[2] == ["git", "checkout"]

    # Final tree was copied to dest.
    assert (dest / "SKILL.md").is_file()


def test_sparse_checkout_empty_subpath_delegates_to_clone(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    with patch("ai_dotfiles.core.git_ops.git_clone") as clone:
        git_sparse_checkout("url", "", dest, branch="main")
    clone.assert_called_once_with("url", dest, branch="main")


def test_sparse_checkout_fallback_full_clone(tmp_path: Path) -> None:
    """If ``sparse-checkout`` fails, fall back to a full clone + copy."""
    dest = tmp_path / "out"
    subpath = "skills/x"
    call_log: list[list[str]] = []

    def side_effect(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        call_log.append(cmd)
        # First clone succeeds (sparse); sparse-checkout fails;
        # the fallback clone (triggered by git_clone -> _run_git) succeeds and
        # seeds the subpath.
        if cmd[:2] == ["git", "clone"] and "--filter=blob:none" in cmd:
            dest_arg = Path(cmd[-1])
            dest_arg.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:2] == ["git", "sparse-checkout"]:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr="unknown subcommand"
            )
        if cmd[:2] == ["git", "clone"]:
            dest_arg = Path(cmd[-1])
            (dest_arg / subpath).mkdir(parents=True, exist_ok=True)
            (dest_arg / subpath / "SKILL.md").write_text("x", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("ai_dotfiles.core.git_ops.subprocess.run", side_effect=side_effect):
        git_sparse_checkout("url", subpath, dest)

    # Must have attempted sparse-checkout and then a plain clone as fallback.
    assert any(c[:2] == ["git", "sparse-checkout"] for c in call_log)
    assert any(
        c[:2] == ["git", "clone"] and "--filter=blob:none" not in c for c in call_log
    )
    assert (dest / "SKILL.md").is_file()


def test_sparse_checkout_missing_subpath_errors(tmp_path: Path) -> None:
    dest = tmp_path / "out"

    def side_effect(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "clone"]:
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with (
        patch("ai_dotfiles.core.git_ops.subprocess.run", side_effect=side_effect),
        pytest.raises(ExternalError, match="subpath"),
    ):
        git_sparse_checkout("url", "does/not/exist", dest)


# ── detect_element_type ────────────────────────────────────────────────────


def test_detect_element_type_skill(tmp_path: Path) -> None:
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Skill", encoding="utf-8")
    assert detect_element_type(skill) == "skill"


def test_detect_element_type_directory_without_skill_md(tmp_path: Path) -> None:
    d = tmp_path / "random"
    d.mkdir()
    (d / "README.md").write_text("hi", encoding="utf-8")
    assert detect_element_type(d) is None


def test_detect_element_type_agent_by_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "reviewer.md"
    f.write_text("---\ntype: agent\nname: reviewer\n---\nbody", encoding="utf-8")
    assert detect_element_type(f) == "agent"


def test_detect_element_type_rule_by_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "style.md"
    f.write_text("---\ntype: rule\n---\n", encoding="utf-8")
    assert detect_element_type(f) == "rule"


def test_detect_element_type_agent_by_directory(tmp_path: Path) -> None:
    d = tmp_path / "agents"
    d.mkdir()
    f = d / "helper.md"
    f.write_text("# Helper\n", encoding="utf-8")
    assert detect_element_type(f) == "agent"


def test_detect_element_type_rule_by_directory(tmp_path: Path) -> None:
    d = tmp_path / "rules"
    d.mkdir()
    f = d / "naming.md"
    f.write_text("# naming\n", encoding="utf-8")
    assert detect_element_type(f) == "rule"


def test_detect_element_type_unknown(tmp_path: Path) -> None:
    f = tmp_path / "plain.md"
    f.write_text("just some markdown\n", encoding="utf-8")
    assert detect_element_type(f) is None


def test_detect_element_type_non_markdown(tmp_path: Path) -> None:
    f = tmp_path / "script.sh"
    f.write_text("#!/bin/sh\n", encoding="utf-8")
    assert detect_element_type(f) is None
