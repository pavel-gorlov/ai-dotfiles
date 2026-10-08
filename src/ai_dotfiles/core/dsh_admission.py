"""Explicit admission of healthy static DSH entries, with original gaps intact."""

from collections.abc import Iterable
from dataclasses import replace

from ai_dotfiles.core.dsh_permissions import DshPermissionPolicy
from ai_dotfiles.core.dsh_render import DshDiagnostic
from ai_dotfiles.core.errors import ConfigError

# These describe rejected source entries, never custody or runtime failures.
# Unknown diagnostics remain fatal until their producer defines safe isolation.
_SKIPPABLE = frozenset(
    {
        "HOOK_UNMAPPED",
        "FIELD_UNMAPPED",
        "INVALID_FIELD",
        "INVALID_FRONTMATTER",
        "INVALID_NATIVE_OPTIONS",
        "PATH_ACTIVATION_UNSUPPORTED",
        "STATIC_PARSE_UNSUPPORTED",
        "TOOL_UNMAPPED",
        "FRONTMATTER_INVALID",
        "SOURCE_UNAVAILABLE",
        "COMMAND_ACTIVATION_UNPROVEN",
        "COMMAND_EXECUTION_UNMAPPED",
        "PERMISSION_UNMAPPED",
        "ENV_INVALID",
        "MCP_INVALID",
        "MCP_FIELD_UNMAPPED",
        "MCP_ENV_UNMAPPED",
        "MCP_TRANSPORT_UNMAPPED",
    }
)


def skipped_diagnostics(
    diagnostics: Iterable[DshDiagnostic],
) -> tuple[DshDiagnostic, ...]:
    """Return original blocking gaps whose affected entries can be omitted."""
    return tuple(
        item for item in diagnostics if item.blocking and item.code in _SKIPPABLE
    )


def require_admission(
    diagnostics: Iterable[DshDiagnostic], *, strict: bool, context: str
) -> None:
    """Reject every gap in strict mode and all integrity/runtime gaps otherwise."""
    refused = refused_diagnostics(diagnostics, strict=strict)
    if refused:
        raise ConfigError(
            context
            + ": "
            + "; ".join(
                f"{item.origin} {item.element} {item.field}: {item.reason}"
                for item in refused
            )
        )


def refused_diagnostics(
    diagnostics: Iterable[DshDiagnostic], *, strict: bool
) -> tuple[DshDiagnostic, ...]:
    """Expose fatal gaps so read-only migration reports remain inspectable."""
    return tuple(
        item
        for item in diagnostics
        if item.blocking and (strict or item.code not in _SKIPPABLE)
    )


def admitted_permissions(
    policy: DshPermissionPolicy, *, strict: bool
) -> DshPermissionPolicy:
    """Keep every exact deny/ask; omitted restrictions stay in the source report.

    This is an effective runtime view, not a rewritten original policy. It
    supplies no grants/presets, and all translated tools still require audit.
    """
    require_admission(
        policy.diagnostics, strict=strict, context="Cannot activate DSH permissions"
    )
    return replace(
        policy, gaps=tuple(gap for gap in policy.gaps if not gap.diagnostic.blocking)
    )
