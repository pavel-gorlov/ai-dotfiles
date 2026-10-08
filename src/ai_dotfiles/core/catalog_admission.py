"""Read-only Codex source admission, separate from ownership and write failures.

The existing renderers prove their required source fields, not arbitrary YAML.
Only their SourceError can become a skipped artifact. All requested target paths
remain available to callers so a failed refresh cannot accidentally prune them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_dotfiles.core import codex_install
from ai_dotfiles.core.codex_layout import CodexLayout
from ai_dotfiles.core.codex_render import (
    render_agent_toml,
    render_rule_skill_md,
    render_skill_md,
)
from ai_dotfiles.core.codex_targets import CodexPair, iter_codex_pairs
from ai_dotfiles.core.elements import Element, ElementType
from ai_dotfiles.core.errors import LinkError, SourceError


@dataclass(frozen=True)
class CodexSourceAdmission:
    """One requested artifact and its source-only validation failure, if any."""

    pair: CodexPair
    element: Element
    error: SourceError | None = None


@dataclass(frozen=True)
class CodexAdmissionReport:
    """Admission decisions with all requested paths, including skipped sources."""

    admissions: tuple[CodexSourceAdmission, ...]

    @property
    def by_pair(self) -> dict[CodexPair, CodexSourceAdmission]:
        """Return per-artifact decisions for existing install/add member loops."""
        return {item.pair: item for item in self.admissions}

    @property
    def admitted_pairs(self) -> tuple[CodexPair, ...]:
        """Return the artifacts whose current sources can be materialized."""
        return tuple(item.pair for item in self.admissions if item.error is None)

    @property
    def skipped(self) -> tuple[CodexSourceAdmission, ...]:
        """Return every failed source with its originating manifest element."""
        return tuple(item for item in self.admissions if item.error is not None)

    @property
    def requested_skills(self) -> frozenset[Path]:
        """Return real/synthetic skill paths to keep during manifest-based prune."""
        return frozenset(
            item.pair.target
            for item in self.admissions
            if item.pair.element_type is not ElementType.AGENT
        )

    @property
    def requested_agents(self) -> frozenset[Path]:
        """Return requested agent paths even when their refresh was skipped."""
        return frozenset(
            item.pair.target
            for item in self.admissions
            if item.pair.element_type is ElementType.AGENT
        )


def _verify_destination(pair: CodexPair) -> None:
    target = pair.target
    for parent in target.absolute().parents:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise LinkError(f"Refusing redirected Codex destination parent: {parent}")
    if target.is_symlink():
        if pair.element_type is ElementType.SKILL:
            try:
                if target.resolve() == pair.source.resolve():
                    return
            except (OSError, RuntimeError) as exc:
                raise LinkError(
                    f"Cannot verify Codex skill link {target}: {exc}"
                ) from exc
        raise LinkError(f"Foreign Codex destination symlink: {target}")
    if not target.exists():
        return
    if pair.element_type is ElementType.AGENT:
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise LinkError(f"Cannot verify Codex agent {target}: {exc}") from exc
        if (
            len(lines) >= 2
            and lines[0] == codex_install.MANAGED_BY_HEADER
            and re.fullmatch(r"# source-sha256: [a-f0-9]{64}", lines[1])
        ):
            return
    elif target.is_dir():
        meta = target / codex_install.SKILL_META_FILENAME
        if meta.is_symlink() or (target / "SKILL.md").is_symlink():
            raise LinkError(f"Refusing redirected Codex skill files: {target}")
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise LinkError(
                f"Cannot verify Codex skill ownership {target}: {exc}"
            ) from exc
        if (
            isinstance(data, dict)
            and data.get("managed_by") == "ai-dotfiles"
            and isinstance(data.get("source_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", data["source_sha256"])
        ):
            return
    raise LinkError(f"Foreign Codex destination; refusing replacement: {target}")


def _validate_source(pair: CodexPair) -> None:
    if pair.element_type is ElementType.SKILL:
        render_skill_md(pair.source / "SKILL.md")
    elif pair.element_type is ElementType.AGENT:
        render_agent_toml(pair.source)
    else:
        render_rule_skill_md(pair.source)


def preflight_codex_pairs(
    parsed: Sequence[Element],
    layout: CodexLayout,
    catalog: Path,
    *,
    strict: bool = False,
) -> CodexAdmissionReport:
    """Classify sources without writes; ownership conflicts always remain fatal.

    Domain members are independent artifacts. Strict mode reports every source
    failure before any caller starts materialization. No YAML capability or
    dependency semantics are inferred beyond the existing Codex renderers.
    """
    admissions: list[CodexSourceAdmission] = []
    destinations: dict[Path, CodexPair] = {}
    for element in parsed:
        for pair in iter_codex_pairs(element, layout, catalog):
            previous = destinations.get(pair.target)
            if previous is not None:
                if previous != pair:
                    raise LinkError(
                        f"Conflicting requested Codex target: {pair.target}"
                    )
                continue
            destinations[pair.target] = pair
            _verify_destination(pair)
            error = None
            try:
                _validate_source(pair)
            except SourceError as exc:
                error = exc
            admissions.append(CodexSourceAdmission(pair, element, error))
    report = CodexAdmissionReport(tuple(admissions))
    if strict and report.skipped:
        raise SourceError(
            "Codex source preflight refused: "
            + "; ".join(str(item.error) for item in report.skipped)
        )
    return report


def apply_admitted_codex_pair(pair: CodexPair, *, global_scope: bool = False) -> str:
    """Recheck one admitted artifact and apply without swallowing write failures.

    A source or destination can change after preflight, so both are verified
    again before the installer creates anything. Callers only invoke this for
    admitted pairs; a newly broken source raises SourceError rather than writing.
    """
    _verify_destination(pair)
    _validate_source(pair)
    if pair.element_type is ElementType.SKILL:
        if (
            global_scope
            and codex_install.skill_symlink_ok(pair.source, pair.target.name)[0]
        ):
            return codex_install.symlink_codex_skill(
                pair.source, pair.target, relative=False
            )
        return codex_install.install_codex_skill(pair.source, pair.target)
    if pair.element_type is ElementType.RULE:
        return codex_install.install_codex_rule_skill(pair.source, pair.target)
    return codex_install.install_codex_agent(pair.source, pair.target)
