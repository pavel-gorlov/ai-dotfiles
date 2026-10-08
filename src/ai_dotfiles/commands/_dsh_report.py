"""Shared presentation of DSH adaptation gaps and partial activation."""

from collections.abc import Iterable

from ai_dotfiles import ui
from ai_dotfiles.core.dsh_admission import skipped_diagnostics
from ai_dotfiles.core.dsh_render import DshDiagnostic


def print_dsh_diagnostics(
    diagnostics: Iterable[DshDiagnostic], *, strict: bool = False, indent: str = ""
) -> None:
    """List every limitation, identifying omitted source contributions clearly."""
    items = tuple(dict.fromkeys(diagnostics))
    skipped = skipped_diagnostics(items)
    for diagnostic in items:
        label = "LIMITATION"
        if diagnostic.blocking:
            label = (
                "SKIPPED ERROR" if diagnostic in skipped and not strict else "BLOCKER"
            )
        ui.warn(
            f"{indent}[{label}] {diagnostic.origin} {diagnostic.element} "
            f"{diagnostic.field}: {diagnostic.reason} [{diagnostic.code}]"
        )
    if skipped and not strict:
        ui.warn(
            f"{indent}DSH activation: PARTIAL ({len(skipped)} adaptation errors). "
            "Supported entries continue; skipped entries stay inactive."
        )
        ui.warn(
            f"{indent}Any skipped hook or permission restriction is not enforced. "
            "Use --strict to refuse partial activation."
        )
