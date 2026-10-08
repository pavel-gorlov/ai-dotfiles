"""``ai-dotfiles reconcile`` — regenerate stale/missing Codex and DSH artefacts.

The missing feedback loop after the first ``install``: catalog changes and
edited local sources leave the Codex trees drifting until a full reinstall.
``reconcile`` regenerates only what is stale or missing (skills, agents, rule
blocks, ``config.toml``, and migrate-origin local artefacts). ``--check``
writes nothing and exits non-zero when drift exists, so it can gate CI /
pre-commit.
"""

from __future__ import annotations

import click

from ai_dotfiles import ui
from ai_dotfiles.commands._dsh_report import print_dsh_diagnostics
from ai_dotfiles.core import codex_reconcile, manifest, paths
from ai_dotfiles.core.catalog_admission import preflight_codex_pairs
from ai_dotfiles.core.codex_layout import global_layout, project_layout
from ai_dotfiles.core.codex_reconcile import ReconcileReport
from ai_dotfiles.core.dsh_migrate import plan_dsh_full_lifecycle
from ai_dotfiles.core.dsh_reconcile import (
    DshReconcileReport,
    apply_dsh_reconciliation,
)
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError


@click.command("reconcile")
@click.option(
    "--check",
    is_flag=True,
    help="Report drift and exit non-zero if any is found; write nothing "
    "(for CI / pre-commit).",
)
@click.option(
    "-g",
    "--global",
    "is_global",
    is_flag=True,
    help="Reconcile global Codex/DSH artefacts in $CODEX_HOME/$DSH_HOME "
    "instead of project artefacts.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Refuse source/adaptation errors, including during --check.",
)
def reconcile(check: bool, is_global: bool, strict: bool = False) -> None:
    """Regenerate stale or missing Codex/DSH artefacts (--check to gate CI)."""
    try:
        if is_global:
            _run_reconcile_global(check=check, strict=strict)
        else:
            _run_reconcile(check=check, strict=strict)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _run_reconcile(*, check: bool, strict: bool = False) -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    manifest_path = paths.project_manifest_path(root)
    packages = manifest.get_packages(manifest_path)
    targets = manifest.get_targets(manifest_path)
    if "codex" in targets:
        preflight_codex_pairs(
            parse_elements(packages),
            project_layout(root),
            paths.catalog_dir(),
            strict=strict,
        )
    dsh_plan = plan_dsh_full_lifecycle(
        root,
        packages,
        paths.catalog_dir(),
        targets,
        mode="copy" if manifest.get_link_mode(manifest_path) == "copy" else "link",
        strict=strict,
    )
    # Refresh shared DSH custody before Codex can change a rule's marker/body.
    issues = (
        _print_report(
            apply_dsh_reconciliation(dsh_plan, check_only=check, strict=strict),
            target="DSH",
        )
        if dsh_plan is not None
        else 0
    )
    report = codex_reconcile.reconcile_codex(
        root,
        packages,
        paths.catalog_dir(),
        check_only=check,
        include_catalog="codex" in targets,
        strict=strict,
    )
    issues += _print_report(report)
    if issues:
        raise SystemExit(1)


def _run_reconcile_global(*, check: bool, strict: bool = False) -> None:
    manifest_path = paths.global_manifest_path()
    targets = manifest.get_targets(manifest_path)
    packages = manifest.get_packages(manifest_path)
    if "codex" in targets:
        preflight_codex_pairs(
            parse_elements(packages),
            global_layout(),
            paths.catalog_dir(),
            strict=strict,
        )
    dsh_plan = plan_dsh_full_lifecycle(
        None, packages, paths.catalog_dir(), targets, strict=strict
    )
    issues = (
        _print_report(
            apply_dsh_reconciliation(dsh_plan, check_only=check, strict=strict),
            fix_cmd="ai-dotfiles reconcile -g",
            target="DSH",
        )
        if dsh_plan is not None
        else 0
    )
    if "codex" not in targets:
        ui.info(
            "Codex is not a global target — nothing to reconcile. "
            '(Add "codex" to "targets" in global.json to opt in.)'
        )
    else:
        report = codex_reconcile.reconcile_codex_global(
            packages, paths.catalog_dir(), check_only=check, strict=strict
        )
        issues += _print_report(report, fix_cmd="ai-dotfiles reconcile -g")
    if issues:
        raise SystemExit(1)


def _print_report(
    report: ReconcileReport | DshReconcileReport,
    fix_cmd: str = "ai-dotfiles reconcile",
    *,
    target: str = "Codex",
) -> int:
    if isinstance(report, DshReconcileReport):
        print_dsh_diagnostics(report.diagnostics, indent="  ")
    elif report.skipped:
        for entry in report.skipped:
            ui.warn(f"[SKIPPED ERROR] Codex {entry.pair.source}: {entry.error}")
        ui.warn(f"Codex reconciliation: PARTIAL ({len(report.skipped)} source errors).")
    if not report.drift:
        partial = (
            report.partial
            if isinstance(report, DshReconcileReport)
            else bool(report.skipped)
        )
        qualifier = "Supported " if partial else ""
        ui.info(f"{qualifier}{target} artefacts up to date.")
        return 0

    ui.info(
        f"{target} drift detected:" if report.check_only else f"{target} reconciled:"
    )
    for label in report.drift:
        ui.info(f"  - {label}")

    if report.check_only:
        noun = "artefact" if len(report.drift) == 1 else "artefacts"
        ui.info(f"{len(report.drift)} stale/missing {noun}. Run '{fix_cmd}'.")
        return 1

    noun = "artefact" if len(report.drift) == 1 else "artefacts"
    ui.info(f"Reconciled {len(report.drift)} {noun}.")
    return 0
