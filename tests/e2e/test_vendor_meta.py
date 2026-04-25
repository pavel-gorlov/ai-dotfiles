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


def test_vendor_list_shows_install_url_for_missing_deps(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001 — AI_DOTFILES_HOME env is enough
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing deps render as ``<name>: x  ->  <install_url>``; installed
    deps keep the bare ``<name>: +`` form."""

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name == "git" else None

    # Cover every vendor module that calls ``shutil.which`` to determine
    # dependency status so the list reflects a deterministic state.
    for module in (
        "ai_dotfiles.vendors.github",
        "ai_dotfiles.vendors.skills_sh",
        "ai_dotfiles.vendors.paks",
        "ai_dotfiles.vendors.buildwithclaude",
        "ai_dotfiles.vendors.tonsofskills",
    ):
        monkeypatch.setattr(f"{module}.shutil.which", fake_which)

    result = runner.invoke(vendor, ["list"])
    assert result.exit_code == 0, result.output
    # Installed dep: bare "+" form.
    assert "git: +" in result.output
    # Missing deps: include install URL with two-space arrows.
    assert "npx: x  ->  https://nodejs.org/" in result.output
    assert "paks: x  ->  https://paks.stakpak.dev" in result.output


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
    """Exit code 1 when git is missing; output includes install URL."""
    _patch_which(monkeypatch, present=set())
    result = runner.invoke(vendor, ["github", "deps", "check"])
    assert result.exit_code == 1, result.output
    assert "git: x missing" in result.output
    assert "https://git-scm.com/" in result.output


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


def test_vendor_skills_sh_search_prints_hits(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vendor skills_sh search <query>` prints source@name + URL per hit."""
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

    result = runner.invoke(vendor, ["skills_sh", "search", "react"])

    assert result.exit_code == 0, result.output
    assert "vercel-labs/agent-skills@vercel-react-best-practices" in result.output
    assert "(321.7K installs)" in result.output
    assert "https://skills.sh/vercel-labs/agent-skills/" in result.output
    assert "alice/skills@thing" in result.output


def test_vendor_skills_sh_search_no_results(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No matches → non-zero exit with error message."""
    _patch_which(monkeypatch, present={"npx"})
    _patch_npx_subprocess(monkeypatch, stdout="nothing here\n")

    result = runner.invoke(vendor, ["skills_sh", "search", "zzznothing"])

    assert result.exit_code != 0
    assert "no results" in result.output.lower()


def test_vendor_github_has_no_search_subcommand(runner: CliRunner) -> None:
    """GitHub vendor does not expose a search subcommand."""
    result = runner.invoke(vendor, ["github", "--help"])
    assert result.exit_code == 0
    assert " search " not in result.output


def test_vendor_skills_sh_deps_check_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 when npx is missing; output includes install URL."""
    _patch_which(monkeypatch, present=set())
    result = runner.invoke(vendor, ["skills_sh", "deps", "check"])
    assert result.exit_code == 1, result.output
    assert "npx: x missing" in result.output
    assert "https://nodejs.org/" in result.output


def test_vendor_skills_sh_deps_check_present(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 0 when npx is installed."""
    _patch_which(monkeypatch, present={"npx"})
    result = runner.invoke(vendor, ["skills_sh", "deps", "check"])
    assert result.exit_code == 0, result.output
    assert "npx: + installed" in result.output


# ── vendor search (aggregated meta command) ──────────────────────────────────


def _patch_which_all(
    monkeypatch: pytest.MonkeyPatch,
    present: set[str],
) -> None:
    """Patch ``shutil.which`` in every vendor module for meta-search tests."""

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in present else None

    for module in (
        "ai_dotfiles.vendors.github",
        "ai_dotfiles.vendors.skills_sh",
        "ai_dotfiles.vendors.paks",
        "ai_dotfiles.vendors.buildwithclaude",
        "ai_dotfiles.vendors.tonsofskills",
    ):
        monkeypatch.setattr(f"{module}.shutil.which", fake_which)


def _stub_all_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every search-capable vendor with a fixed, vendor-native hit list."""
    from ai_dotfiles.vendors import (
        BUILDWITHCLAUDE,
        PAKS,
        SKILLS_SH,
        TONSOFSKILLS,
    )
    from ai_dotfiles.vendors import buildwithclaude as bwc_mod
    from ai_dotfiles.vendors import paks as paks_mod
    from ai_dotfiles.vendors import skills_sh as skillssh_mod
    from ai_dotfiles.vendors import tonsofskills as tos_mod

    def skills_sh_search(self: object, query: str) -> list[object]:
        return [
            skillssh_mod.SearchResult(
                source="vercel-labs/agent-skills",
                name="react-best-practices",
                installs="321.7K",
                url="https://skills.sh/vercel-labs/react",
            ),
        ]

    def paks_search(self: object, query: str) -> list[object]:
        return [
            paks_mod.SearchResult(
                source="wshpbson",
                name="k8s-manifest-generator",
                description="Generate k8s manifests",
                url="https://paks.stakpak.dev/wshpbson/k8s",
                installs="42",
            ),
        ]

    def bwc_search(self: object, query: str) -> list[object]:
        return [
            bwc_mod.SearchResult(
                source="buildwithclaude",
                name="bwc-skill",
                description="Something useful",
                url="https://github.com/davepoon/buildwithclaude/tree/main/bwc",
            ),
        ]

    def tos_search(self: object, query: str) -> list[object]:
        return [
            tos_mod.SearchResult(
                source="tonsofskills",
                name="tos-skill",
                description="Tons of skill",
                url="https://github.com/jeremylongshore/tos/tree/main/plugins/tos",
            ),
        ]

    monkeypatch.setattr(type(SKILLS_SH), "search", skills_sh_search, raising=True)
    monkeypatch.setattr(type(PAKS), "search", paks_search, raising=True)
    monkeypatch.setattr(type(BUILDWITHCLAUDE), "search", bwc_search, raising=True)
    monkeypatch.setattr(type(TONSOFSKILLS), "search", tos_search, raising=True)


def test_vendor_meta_search_aggregates_across_vendors(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every search-capable vendor contributes a section; github is absent."""
    _patch_which_all(monkeypatch, present={"git", "npx", "paks"})
    _stub_all_searches(monkeypatch)

    result = runner.invoke(vendor, ["search", "anything"])
    assert result.exit_code == 0, result.output

    assert "=== skills_sh (1 results) ===" in result.output
    assert "=== paks (1 results) ===" in result.output
    assert "=== buildwithclaude (1 results) ===" in result.output
    assert "=== tonsofskills (1 results) ===" in result.output
    # URLs from each stub appear.
    assert "https://skills.sh/vercel-labs/react" in result.output
    assert "https://paks.stakpak.dev/wshpbson/k8s" in result.output
    assert "https://github.com/davepoon/buildwithclaude/tree/main/bwc" in result.output
    assert (
        "https://github.com/jeremylongshore/tos/tree/main/plugins/tos" in result.output
    )
    # github has no search method — no section header.
    assert "=== github" not in result.output


def test_vendor_meta_search_skips_vendors_with_missing_deps(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vendors whose deps are absent print a 'skipped' header and are not queried."""
    # Only git is present → skills_sh (npx) and paks (paks CLI) are skipped.
    _patch_which_all(monkeypatch, present={"git"})
    _stub_all_searches(monkeypatch)

    result = runner.invoke(vendor, ["search", "x"])
    assert result.exit_code == 0, result.output

    assert (
        "=== skills_sh — skipped (deps missing: npx  ->  https://nodejs.org/) ==="
        in result.output
    )
    assert (
        "=== paks — skipped (deps missing: paks  ->  https://paks.stakpak.dev) ==="
        in result.output
    )
    # Git-backed vendors produce real sections.
    assert "=== buildwithclaude (1 results) ===" in result.output
    assert "=== tonsofskills (1 results) ===" in result.output


def test_vendor_meta_search_filter_by_vendor(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``-v`` restricts which vendors are queried."""
    _patch_which_all(monkeypatch, present={"git", "npx", "paks"})
    _stub_all_searches(monkeypatch)

    result = runner.invoke(
        vendor, ["search", "anything", "-v", "paks", "-v", "skills_sh"]
    )
    assert result.exit_code == 0, result.output
    assert "=== skills_sh (1 results) ===" in result.output
    assert "=== paks (1 results) ===" in result.output
    assert "=== buildwithclaude" not in result.output
    assert "=== tonsofskills" not in result.output

    # Restricting to github (no search method) → zero targets → "No results."
    result2 = runner.invoke(vendor, ["search", "anything", "--vendor", "github"])
    assert result2.exit_code == 0, result2.output
    assert "No results." in result2.output
    assert "=== github" not in result2.output


def test_vendor_meta_search_limit_applied(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--limit N`` trims each vendor to N rows."""
    from ai_dotfiles.vendors import PAKS
    from ai_dotfiles.vendors import paks as paks_mod

    _patch_which_all(monkeypatch, present={"paks"})

    def paks_search(self: object, query: str) -> list[object]:
        return [
            paks_mod.SearchResult(
                source="owner",
                name=f"skill-{i:02d}",
                description="",
                url=f"https://paks.stakpak.dev/owner/skill-{i:02d}",
                installs="",
            )
            for i in range(50)
        ]

    monkeypatch.setattr(type(PAKS), "search", paks_search, raising=True)

    result = runner.invoke(vendor, ["search", "anything", "-v", "paks", "--limit", "3"])
    assert result.exit_code == 0, result.output
    assert "=== paks (3 results) ===" in result.output
    assert "skill-00" in result.output
    assert "skill-01" in result.output
    assert "skill-02" in result.output
    # Row 3 must be trimmed.
    assert "skill-03" not in result.output


def test_vendor_meta_search_vendor_error_continues(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising vendor becomes a warning; others still render."""
    from ai_dotfiles.vendors import PAKS, SKILLS_SH

    _patch_which_all(monkeypatch, present={"npx", "paks"})
    _stub_all_searches(monkeypatch)

    def boom(self: object, query: str) -> list[object]:
        raise RuntimeError("boom")

    # skills_sh blows up; paks keeps its stubbed result.
    monkeypatch.setattr(type(SKILLS_SH), "search", boom, raising=True)

    result = runner.invoke(vendor, ["search", "x", "-v", "skills_sh", "-v", "paks"])
    assert result.exit_code == 0, result.output
    assert "=== skills_sh — error: boom ===" in result.output
    assert "=== paks (1 results) ===" in result.output
    # Sanity: the other vendor's data still reached stdout.
    assert "k8s-manifest-generator" in result.output
    # PAKS is still a frozen dataclass type after monkeypatch — no leakage needed.
    _ = PAKS


def test_vendor_meta_search_unknown_vendor_errors(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``-v <unknown>`` aborts with a UsageError (non-zero exit)."""
    _patch_which_all(monkeypatch, present={"git", "npx", "paks"})
    result = runner.invoke(vendor, ["search", "x", "-v", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output


def test_vendor_meta_search_empty_query(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / whitespace-only query aborts with a UsageError."""
    _patch_which_all(monkeypatch, present={"git", "npx", "paks"})
    result = runner.invoke(vendor, ["search", ""])
    assert result.exit_code != 0
    assert "empty" in result.output.lower()


def test_vendor_meta_search_no_matches_anywhere(
    runner: CliRunner,
    tmp_storage: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All vendors empty → headers + ``(no matches)`` + final ``No results.``."""
    from ai_dotfiles.vendors import (
        BUILDWITHCLAUDE,
        PAKS,
        SKILLS_SH,
        TONSOFSKILLS,
    )

    _patch_which_all(monkeypatch, present={"git", "npx", "paks"})

    def empty(self: object, query: str) -> list[object]:
        return []

    for vendor_singleton in (SKILLS_SH, PAKS, BUILDWITHCLAUDE, TONSOFSKILLS):
        monkeypatch.setattr(type(vendor_singleton), "search", empty, raising=True)

    result = runner.invoke(vendor, ["search", "zzzzzz"])
    assert result.exit_code == 0, result.output
    # Section headers present for each active vendor.
    assert "=== skills_sh (0 results) ===" in result.output
    assert "=== paks (0 results) ===" in result.output
    assert "=== buildwithclaude (0 results) ===" in result.output
    assert "=== tonsofskills (0 results) ===" in result.output
    # Each empty section has the placeholder line.
    assert result.output.count("(no matches)") >= 4
    # Table headers must NOT appear — no body was rendered.
    assert "NAME  INSTALLS" not in result.output
    # Final fallback line.
    assert "No results." in result.output
