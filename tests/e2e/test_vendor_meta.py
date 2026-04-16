"""End-to-end tests for the new ``ai-dotfiles vendor`` click group.

Covers:

* Meta subcommands: ``vendor list``, ``vendor installed``, ``vendor remove``.
* Per-vendor subgroups for ``github`` (``install`` / ``list`` / ``deps``)
  and ``skills_sh`` (``install`` / ``deps``).

The upstream GitHub and npx CLIs are mocked to avoid network + npm access.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.vendor import vendor


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── helpers ──────────────────────────────────────────────────────────────────


def _catalog(storage: Path) -> Path:
    return storage / "catalog"


def _write_fake_source(
    item_dir: Path,
    *,
    vendor_name: str = "github",
    origin: str = "github:acme/tools/skills/foo",
    tool: str = "ai-dotfiles vendor",
    fetched: str = "2026-04-15",
    license_: str = "unknown",
) -> None:
    item_dir.mkdir(parents=True, exist_ok=True)
    (item_dir / ".source").write_text(
        "\n".join(
            [
                f"vendor: {vendor_name}",
                f"origin: {origin}",
                f"tool: {tool}",
                f"fetched: {fetched}",
                f"license: {license_}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _patch_github_sparse_checkout(
    monkeypatch: pytest.MonkeyPatch,
    *,
    as_skill: bool = True,
) -> None:
    """Replace ``git_ops.git_sparse_checkout`` to lay down a fake skill tree."""

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        dest.mkdir(parents=True, exist_ok=False)
        if as_skill:
            (dest / "SKILL.md").write_text("# fake skill\n", encoding="utf-8")
        else:
            (dest / "README.md").write_text("# readme\n", encoding="utf-8")

    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout",
        fake_checkout,
    )


def _patch_which(
    monkeypatch: pytest.MonkeyPatch,
    present: set[str],
) -> None:
    """Patch ``shutil.which`` in both vendor modules to only report ``present``."""

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in present else None

    monkeypatch.setattr("ai_dotfiles.vendors.github.shutil.which", fake_which)
    monkeypatch.setattr("ai_dotfiles.vendors.skills_sh.shutil.which", fake_which)


def _patch_npx_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    materialize: dict[str, dict[str, str]] | None = None,
    captured: dict[str, Any] | None = None,
) -> None:
    """Patch ``subprocess.run`` inside ``vendors.skills_sh``."""

    def fake_run(
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if captured is not None:
            captured["argv"] = list(argv)
            captured["env"] = dict(env) if env is not None else None

        if materialize is not None and env is not None:
            home = Path(env["HOME"])
            skills_root = home / ".claude" / "skills"
            skills_root.mkdir(parents=True, exist_ok=True)
            for name, files in materialize.items():
                skill_dir = skills_root / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                for fname, body in files.items():
                    (skill_dir / fname).write_text(body, encoding="utf-8")

        return subprocess.CompletedProcess(
            args=argv, returncode=returncode, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr("ai_dotfiles.vendors.skills_sh.subprocess.run", fake_run)


# ── vendor list ──────────────────────────────────────────────────────────────


def test_vendor_list_shows_both_vendors_with_deps(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001 — AI_DOTFILES_HOME env is enough
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both vendors appear with deps status reflecting ``shutil.which``."""
    _patch_which(monkeypatch, present={"git"})

    result = runner.invoke(vendor, ["list"])
    assert result.exit_code == 0, result.output
    # Headers.
    assert "NAME" in result.output
    assert "DESCRIPTION" in result.output
    assert "DEPS" in result.output
    # Both vendors.
    assert "github" in result.output
    assert "skills_sh" in result.output
    # Deps status reflects patched which.
    assert "git: +" in result.output
    assert "npx: x" in result.output


# ── vendor installed ─────────────────────────────────────────────────────────


def test_vendor_installed_empty_catalog(runner: CliRunner, tmp_storage: Path) -> None:
    """Empty catalog → friendly 'No vendored items.' message."""
    _catalog(tmp_storage).mkdir(parents=True, exist_ok=True)
    result = runner.invoke(vendor, ["installed"])
    assert result.exit_code == 0, result.output
    assert "No vendored items." in result.output


def test_vendor_installed_lists_catalog_entries(
    runner: CliRunner, tmp_storage: Path
) -> None:
    """Items with a ``.source`` appear; items without are skipped."""
    catalog = _catalog(tmp_storage)
    # Vendored skill with .source.
    _write_fake_source(
        catalog / "skills" / "foo",
        origin="github:acme/tools/skills/foo",
        fetched="2026-04-15",
    )
    # Another vendored skill (via skills_sh).
    _write_fake_source(
        catalog / "skills" / "bar",
        vendor_name="skills_sh",
        origin="skills_sh:vercel-labs/skills",
        fetched="2026-04-14",
    )
    # Non-vendored: no .source file, should be skipped.
    (catalog / "skills" / "local-only").mkdir(parents=True, exist_ok=True)

    result = runner.invoke(vendor, ["installed"])
    assert result.exit_code == 0, result.output
    assert "foo" in result.output
    assert "bar" in result.output
    assert "local-only" not in result.output
    # Columns present.
    assert "NAME" in result.output
    assert "KIND" in result.output
    assert "VENDOR" in result.output
    assert "ORIGIN" in result.output
    assert "FETCHED" in result.output
    # Sorted by kind then name → bar comes before foo.
    assert result.output.index("bar") < result.output.index("foo")


# ── vendor remove ────────────────────────────────────────────────────────────


def test_vendor_remove_deletes_entry(runner: CliRunner, tmp_storage: Path) -> None:
    """``remove --yes`` deletes the catalog directory."""
    catalog = _catalog(tmp_storage)
    target = catalog / "skills" / "foo"
    _write_fake_source(target)

    result = runner.invoke(vendor, ["remove", "foo", "--yes"])
    assert result.exit_code == 0, result.output
    assert not target.exists()
    assert "Removed" in result.output


def test_vendor_remove_warns_when_referenced_in_stack(
    runner: CliRunner, tmp_storage: Path
) -> None:
    """If the element is used by a stack, a warning is emitted before deletion."""
    catalog = _catalog(tmp_storage)
    target = catalog / "skills" / "foo"
    _write_fake_source(target)

    stacks = tmp_storage / "stacks"
    stacks.mkdir(parents=True, exist_ok=True)
    (stacks / "demo.conf").write_text("skill:foo\n", encoding="utf-8")

    result = runner.invoke(vendor, ["remove", "foo", "--yes"])
    assert result.exit_code == 0, result.output
    assert "used in" in result.output
    assert "stacks/demo.conf" in result.output
    assert not target.exists()


def test_vendor_remove_missing_raises_element_error(
    runner: CliRunner, tmp_storage: Path
) -> None:
    """Remove with no match exits non-zero with a helpful message."""
    _catalog(tmp_storage).mkdir(parents=True, exist_ok=True)
    result = runner.invoke(vendor, ["remove", "nonexistent", "--yes"])
    assert result.exit_code != 0
    assert "No vendored item named 'nonexistent'" in result.output


def test_vendor_remove_ambiguous_requires_kind(
    runner: CliRunner, tmp_storage: Path
) -> None:
    """Same name under multiple kinds requires ``--kind``."""
    catalog = _catalog(tmp_storage)
    _write_fake_source(catalog / "skills" / "dup")
    _write_fake_source(
        catalog / "agents" / "dup",
        origin="github:acme/tools/agents/dup",
    )

    result = runner.invoke(vendor, ["remove", "dup", "--yes"])
    assert result.exit_code != 0
    assert "Ambiguous" in result.output
    assert "--kind" in result.output

    # Disambiguate via --kind.
    result2 = runner.invoke(vendor, ["remove", "dup", "--kind", "skill", "--yes"])
    assert result2.exit_code == 0, result2.output
    assert not (catalog / "skills" / "dup").exists()
    assert (catalog / "agents" / "dup").is_dir()


def test_vendor_remove_aborts_on_declined_confirmation(
    runner: CliRunner, tmp_storage: Path
) -> None:
    """Without ``--yes``, answering 'n' leaves the directory in place."""
    catalog = _catalog(tmp_storage)
    target = catalog / "skills" / "foo"
    _write_fake_source(target)

    result = runner.invoke(vendor, ["remove", "foo"], input="n\n")
    assert result.exit_code == 0, result.output
    assert target.exists()
    assert "Aborted" in result.output


# ── vendor github install / list / deps ──────────────────────────────────────


def test_vendor_github_install_happy_path(
    runner: CliRunner,
    tmp_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock sparse checkout → catalog/skills/<name>/.source materializes."""
    _patch_which(monkeypatch, present={"git"})
    _patch_github_sparse_checkout(monkeypatch)

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, ["github", "install", url])
    assert result.exit_code == 0, result.output

    dest = _catalog(tmp_storage) / "skills" / "frontend-design"
    assert dest.is_dir()
    assert (dest / "SKILL.md").is_file()
    source = dest / ".source"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    assert "vendor: github" in text
    assert "origin: github:acme/tools/skills/frontend-design" in text
    assert "Installed catalog/skills/frontend-design/" in result.output
    assert "ai-dotfiles add skill:frontend-design" in result.output


def test_vendor_github_install_existing_dest_no_force(
    runner: CliRunner,
    tmp_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``--force`` the existing destination blocks installation."""
    _patch_which(monkeypatch, present={"git"})
    _patch_github_sparse_checkout(monkeypatch)

    existing = _catalog(tmp_storage) / "skills" / "frontend-design"
    existing.mkdir(parents=True, exist_ok=True)
    (existing / "SKILL.md").write_text("already here", encoding="utf-8")

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, ["github", "install", url])
    assert result.exit_code != 0
    assert "Already exists" in result.output
    assert (existing / "SKILL.md").read_text() == "already here"


def test_vendor_github_install_force_overwrites(
    runner: CliRunner,
    tmp_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--force`` overwrites an existing catalog entry."""
    _patch_which(monkeypatch, present={"git"})
    _patch_github_sparse_checkout(monkeypatch)

    existing = _catalog(tmp_storage) / "skills" / "frontend-design"
    existing.mkdir(parents=True, exist_ok=True)
    (existing / "SKILL.md").write_text("already here", encoding="utf-8")

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, ["github", "install", url, "--force"])
    assert result.exit_code == 0, result.output
    assert (existing / "SKILL.md").read_text().startswith("# fake skill")


def test_vendor_github_install_missing_git_raises(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``git`` is absent, ``deps.ensure`` surfaces a clear error."""
    _patch_which(monkeypatch, present=set())

    url = "https://github.com/acme/tools/tree/main/skills/frontend-design"
    result = runner.invoke(vendor, ["github", "install", url])
    assert result.exit_code != 0
    assert "missing required dependencies" in result.output
    assert "git" in result.output


def test_vendor_github_list_prints_entries(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``vendor github list <url>`` prints each discovered entry on its own line."""
    _patch_which(monkeypatch, present={"git"})

    def fake_checkout(
        repo_url: str,
        subpath: str,
        dest: Path,
        branch: str | None = None,
    ) -> None:
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "alpha").mkdir()
        (dest / "beta").mkdir()

    monkeypatch.setattr(
        "ai_dotfiles.vendors.github.git_ops.git_sparse_checkout", fake_checkout
    )

    url = "https://github.com/acme/tools/tree/main/skills"
    result = runner.invoke(vendor, ["github", "list", url])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_vendor_github_deps_check_git_present(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit code 0 when git is available."""
    _patch_which(monkeypatch, present={"git"})
    result = runner.invoke(vendor, ["github", "deps", "check"])
    assert result.exit_code == 0, result.output
    assert "git: + installed" in result.output


def test_vendor_github_deps_check_git_absent(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit code 1 when git is missing."""
    _patch_which(monkeypatch, present=set())
    result = runner.invoke(vendor, ["github", "deps", "check"])
    assert result.exit_code == 1, result.output
    assert "git: x missing" in result.output


# ── vendor skills_sh install / deps ─────────────────────────────────────────


def test_vendor_skills_sh_install_happy_path(
    runner: CliRunner,
    tmp_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock subprocess materializes skills under HOME, which then get placed."""
    _patch_which(monkeypatch, present={"npx"})
    _patch_npx_subprocess(
        monkeypatch,
        materialize={
            "alpha": {"SKILL.md": "# alpha\n"},
            "beta": {"SKILL.md": "# beta\n"},
        },
    )

    result = runner.invoke(vendor, ["skills_sh", "install", "vercel-labs/skills"])
    assert result.exit_code == 0, result.output

    catalog = _catalog(tmp_storage)
    assert (catalog / "skills" / "alpha" / "SKILL.md").is_file()
    assert (catalog / "skills" / "beta" / "SKILL.md").is_file()
    alpha_source = (catalog / "skills" / "alpha" / ".source").read_text(
        encoding="utf-8"
    )
    assert "vendor: skills_sh" in alpha_source
    assert "origin: skills_sh:vercel-labs/skills" in alpha_source
    assert "Installed catalog/skills/alpha/" in result.output
    assert "Installed catalog/skills/beta/" in result.output


def test_vendor_skills_sh_install_select_parsed(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--select`` is parsed and forwarded as ``-s`` to npx."""
    captured: dict[str, Any] = {}
    _patch_which(monkeypatch, present={"npx"})
    _patch_npx_subprocess(
        monkeypatch,
        materialize={"one": {"SKILL.md": "# one\n"}, "two": {"SKILL.md": "# two\n"}},
        captured=captured,
    )

    result = runner.invoke(
        vendor,
        [
            "skills_sh",
            "install",
            "vercel-labs/skills",
            "--select",
            "one, two",
        ],
    )
    assert result.exit_code == 0, result.output
    argv: list[str] = captured["argv"]
    assert "--skill" in argv
    s_idx = argv.index("--skill")
    assert argv[s_idx + 1 : s_idx + 3] == ["one", "two"]


def test_vendor_skills_sh_install_empty_select_entry_rejected(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty entry in ``--select`` is rejected before invoking subprocess."""
    _patch_which(monkeypatch, present={"npx"})
    result = runner.invoke(
        vendor,
        [
            "skills_sh",
            "install",
            "vercel-labs/skills",
            "--select",
            "one,,two",
        ],
    )
    assert result.exit_code != 0
    assert "empty entry" in result.output


def test_vendor_skills_sh_find_prints_hits(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vendor skills_sh find <query>` prints source@name + URL per hit."""
    _patch_which(monkeypatch, present={"npx"})
    stdout = (
        "vercel-labs/agent-skills@vercel-react-best-practices 321.7K installs\n"
        "\u2514 https://skills.sh/vercel-labs/agent-skills/"
        "vercel-react-best-practices\n"
        "\n"
        "alice/skills@thing\n"
        "\u2514 https://skills.sh/alice/skills/thing\n"
    )
    _patch_npx_subprocess(monkeypatch, stdout=stdout)

    result = runner.invoke(vendor, ["skills_sh", "find", "react"])

    assert result.exit_code == 0, result.output
    assert "vercel-labs/agent-skills@vercel-react-best-practices" in result.output
    assert "(321.7K installs)" in result.output
    assert "https://skills.sh/vercel-labs/agent-skills/" in result.output
    assert "alice/skills@thing" in result.output


def test_vendor_skills_sh_find_no_results(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No matches → non-zero exit with error message."""
    _patch_which(monkeypatch, present={"npx"})
    _patch_npx_subprocess(monkeypatch, stdout="nothing here\n")

    result = runner.invoke(vendor, ["skills_sh", "find", "zzznothing"])

    assert result.exit_code != 0
    assert "no results" in result.output.lower()


def test_vendor_github_has_no_find_subcommand(runner: CliRunner) -> None:
    """GitHub vendor does not expose a find subcommand."""
    result = runner.invoke(vendor, ["github", "--help"])
    assert result.exit_code == 0
    assert " find " not in result.output


def test_vendor_skills_sh_deps_check_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 when npx is missing."""
    _patch_which(monkeypatch, present=set())
    result = runner.invoke(vendor, ["skills_sh", "deps", "check"])
    assert result.exit_code == 1, result.output
    assert "npx: x missing" in result.output


def test_vendor_skills_sh_deps_check_present(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 0 when npx is installed."""
    _patch_which(monkeypatch, present={"npx"})
    result = runner.invoke(vendor, ["skills_sh", "deps", "check"])
    assert result.exit_code == 0, result.output
    assert "npx: + installed" in result.output
