"""Source failures are partial; destination integrity remains a fatal boundary."""

from pathlib import Path

import pytest

from ai_dotfiles.core import codex_install
from ai_dotfiles.core.catalog_admission import (
    apply_admitted_codex_pair,
    preflight_codex_pairs,
)
from ai_dotfiles.core.codex_layout import global_layout, project_layout
from ai_dotfiles.core.codex_targets import CodexPair
from ai_dotfiles.core.elements import ElementType, parse_elements
from ai_dotfiles.core.errors import ElementError, LinkError, SourceError

pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _skill(directory: Path, description: str = "Useful. More context.") -> Path:
    _write(
        directory / "SKILL.md",
        f"---\nname: {directory.name}\ndescription: {description}\n---\nBody\n",
    )
    return directory


def _agent(path: Path, description: str = "Useful agent.") -> Path:
    return _write(
        path,
        f"---\nname: {path.stem}\ndescription: {description}\n---\nPersona\n",
    )


@pytest.mark.parametrize("domain", [False, True])
def test_broken_sources_do_not_stop_healthy_siblings(
    tmp_path: Path, domain: bool
) -> None:
    catalog = tmp_path / "catalog"
    origin = catalog / "bundle" if domain else catalog
    _skill(origin / "skills/good")
    _skill(origin / "skills/bad", "[not, a-scalar]")
    _agent(origin / "agents/good-agent.md")
    _write(origin / "agents/bad-agent.md", "---\nname: bad-agent\n---\nPersona\n")
    names = (
        ["@bundle"]
        if domain
        else ["skill:bad", "skill:good", "agent:bad-agent", "agent:good-agent"]
    )
    layout = project_layout(tmp_path / "project")
    report = preflight_codex_pairs(parse_elements(names), layout, catalog)
    assert len(report.skipped) == 2
    assert all(isinstance(item.error, SourceError) for item in report.skipped)
    assert all(isinstance(item.error, ElementError) for item in report.skipped)
    assert {item.pair.target.name for item in report.skipped} == {
        "bad",
        "bad-agent.toml",
    }
    assert layout.skills_dir / "bad" in report.requested_skills
    assert layout.agents_dir / "bad-agent.toml" in report.requested_agents
    assert len(report.by_pair) == 4
    assert not layout.codex_dir.exists()
    for pair in report.admitted_pairs:
        apply_admitted_codex_pair(pair)
    assert (layout.skills_dir / "good/SKILL.md").is_file()
    assert (layout.agents_dir / "good-agent.toml").is_file()
    assert not (layout.skills_dir / "bad").exists()
    assert not (layout.agents_dir / "bad-agent.toml").exists()


def test_strict_preflight_refuses_all_sources_before_writes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog / "skills/good")
    _write(catalog / "skills/bad/SKILL.md", "---\nname: bad\n")
    _write(catalog / "agents/bad.md", "Persona without frontmatter\n")
    root = tmp_path / "project"
    with pytest.raises(SourceError) as error:
        preflight_codex_pairs(
            parse_elements(["skill:good", "skill:bad", "agent:bad"]),
            project_layout(root),
            catalog,
            strict=True,
        )
    assert "skills/bad/SKILL.md" in str(error.value)
    assert "agents/bad.md" in str(error.value)
    assert not root.exists()


@pytest.mark.parametrize("failure", ["missing", "utf8", "unreadable"])
def test_unreadable_source_is_a_source_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    catalog = tmp_path / "catalog"
    skill = catalog / "skills/bad"
    skill.mkdir(parents=True)
    instruction = skill / "SKILL.md"
    if failure == "utf8":
        instruction.write_bytes(b"\xff")
    elif failure == "unreadable":
        _skill(skill)
        original = Path.read_text

        def read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path == instruction:
                raise PermissionError("source access denied")
            return original(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", read_text)
    report = preflight_codex_pairs(
        parse_elements(["skill:bad"]), project_layout(tmp_path / "out"), catalog
    )
    assert len(report.skipped) == 1
    assert "Cannot read Codex source" in str(report.skipped[0].error)
    assert not report.admitted_pairs


def test_repair_retries_source_and_keeps_requested_existing_output(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    source = _skill(catalog / "skills/example")
    layout = project_layout(tmp_path / "out")
    parsed = parse_elements(["skill:example"])
    initial = preflight_codex_pairs(parsed, layout, catalog)
    apply_admitted_codex_pair(initial.admitted_pairs[0])
    target = layout.skills_dir / "example"
    before = (target / "SKILL.md").read_bytes()
    _write(source / "SKILL.md", "Broken source without frontmatter\n")
    skipped = preflight_codex_pairs(parsed, layout, catalog)
    assert skipped.requested_skills == {target}
    assert skipped.skipped and (target / "SKILL.md").read_bytes() == before
    _skill(source, "Repaired. Extra context.")
    repaired = preflight_codex_pairs(parsed, layout, catalog, strict=True)
    assert not repaired.skipped
    assert apply_admitted_codex_pair(repaired.admitted_pairs[0]) == "updated"
    assert "Repaired." in (target / "SKILL.md").read_text()


def test_global_gate_preserves_raw_link_and_over_cap_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    catalog = tmp_path / "catalog"
    short = _skill(catalog / "skills/short")
    _skill(catalog / "skills/long", "First sentence. " + "x" * 1100)
    _skill(catalog / "skills/bad", "[not, scalar]")
    layout = global_layout()
    report = preflight_codex_pairs(
        parse_elements(["skill:short", "skill:long", "skill:bad"]), layout, catalog
    )
    for pair in report.admitted_pairs:
        apply_admitted_codex_pair(pair, global_scope=True)
    target = layout.skills_dir / "short"
    assert target.is_symlink() and target.readlink() == short
    assert (
        apply_admitted_codex_pair(report.admitted_pairs[0], global_scope=True)
        == "already-linked"
    )
    assert not (layout.skills_dir / "long").is_symlink()
    assert (
        'description: "First sentence."'
        in (layout.skills_dir / "long/SKILL.md").read_text()
    )
    assert not (layout.skills_dir / "bad").exists()
    assert not codex_install.skill_symlink_ok(catalog / "skills/bad", "bad")[0]


@pytest.mark.parametrize("header", ["name: example", "description: [invalid]"])
def test_global_gate_never_links_missing_or_nonstring_description(
    tmp_path: Path, header: str
) -> None:
    source = tmp_path / "example"
    _write(source / "SKILL.md", f"---\n{header}\n---\nBody\n")
    assert not codex_install.skill_symlink_ok(source, "example")[0]


@pytest.mark.parametrize("kind", ["directory", "link", "agent", "parent"])
def test_foreign_destinations_are_fatal_even_with_bad_sources(
    tmp_path: Path, kind: str
) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog / "skills/good")
    _skill(catalog / "skills/bad", "[invalid]")
    _write(catalog / "agents/bad.md", "Invalid agent source\n")
    layout = project_layout(tmp_path / "out")
    foreign = _skill(tmp_path / "foreign", "Personal source.")
    target = layout.skills_dir / "bad"
    if kind == "directory":
        _write(target / "SKILL.md", "Personal skill\n")
    elif kind == "link":
        target.parent.mkdir(parents=True)
        target.symlink_to(foreign)
    elif kind == "agent":
        _write(layout.agents_dir / "bad.toml", 'name = "personal"\n')
    else:
        layout.skills_dir.parent.mkdir(parents=True)
        layout.skills_dir.symlink_to(foreign)
    original = (foreign / "SKILL.md").read_bytes()
    with pytest.raises(LinkError):
        preflight_codex_pairs(
            parse_elements(["skill:good", "skill:bad", "agent:bad"]), layout, catalog
        )
    assert (foreign / "SKILL.md").read_bytes() == original
    assert not (layout.agents_dir / "good.toml").exists()
    assert not (layout.skills_dir / "good/SKILL.md").exists()


def test_duplicate_target_origins_are_not_source_skips(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog / "one/skills/example")
    _skill(catalog / "two/skills/example")
    root = tmp_path / "out"
    with pytest.raises(LinkError, match="Conflicting requested Codex target"):
        preflight_codex_pairs(
            parse_elements(["@one", "@two"]), project_layout(root), catalog
        )
    assert not root.exists()


def test_apply_rechecks_destination_and_propagates_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "catalog"
    source = _skill(catalog / "skills/example")
    layout = project_layout(tmp_path / "out")
    report = preflight_codex_pairs(parse_elements(["skill:example"]), layout, catalog)
    pair = report.admitted_pairs[0]
    personal = _write(pair.target / "SKILL.md", "Personal skill\n")
    with pytest.raises(LinkError):
        apply_admitted_codex_pair(pair)
    assert personal.read_text() == "Personal skill\n"

    def fail_write(source_dir: Path, target_dir: Path) -> str:
        raise LinkError("write failed")

    monkeypatch.setattr(codex_install, "install_codex_skill", fail_write)
    other = CodexPair(ElementType.SKILL, source, layout.skills_dir / "other")
    with pytest.raises(LinkError, match="write failed"):
        apply_admitted_codex_pair(other)


def test_apply_revalidates_a_newly_broken_source_before_writing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    source = _skill(catalog / "skills/example")
    layout = project_layout(tmp_path / "out")
    report = preflight_codex_pairs(parse_elements(["skill:example"]), layout, catalog)
    _write(source / "SKILL.md", "Broken\n")
    with pytest.raises(SourceError):
        apply_admitted_codex_pair(report.admitted_pairs[0])
    assert not layout.skills_dir.exists()
