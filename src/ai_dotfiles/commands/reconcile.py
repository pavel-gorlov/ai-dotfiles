"""``ai-dotfiles reconcile`` — regenerate stale/missing Codex artefacts.

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
from ai_dotfiles.core import codex_reconcile, manifest, paths
from ai_dotfiles.core.codex_reconcile import ReconcileReport
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError


@click.command("reconcile")
@click.option(
    "--check",
    is_flag=True,
    help="Report drift and exit non-zero if any is found; write nothing "
    "(for CI / pre-commit).",
)
def reconcile(check: bool) -> None:
    """Regenerate stale or missing Codex artefacts (--check to gate CI)."""
    try:
        _run_reconcile(check=check)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _run_reconcile(*, check: bool) -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    manifest_path = paths.project_manifest_path(root)
    packages = manifest.get_packages(manifest_path)
    targets = manifest.get_targets(manifest_path)
    report = codex_reconcile.reconcile_codex(
        root,
        packages,
        paths.catalog_dir(),
        check_only=check,
        include_catalog="codex" in targets,
    )
    _print_report(report)


def _print_report(report: ReconcileReport) -> None:
    if not report.drift:
        ui.info("Codex artefacts up to date.")
        return

    ui.info("Drift detected:" if report.check_only else "Reconciled:")
    for label in report.drift:
        ui.info(f"  - {label}")

    if report.check_only:
        noun = "artefact" if len(report.drift) == 1 else "artefacts"
        ui.info(
            f"{len(report.drift)} stale/missing {noun}. Run 'ai-dotfiles reconcile'."
        )
        raise SystemExit(1)

    noun = "artefact" if len(report.drift) == 1 else "artefacts"
    ui.info(f"Reconciled {len(report.drift)} {noun}.")
