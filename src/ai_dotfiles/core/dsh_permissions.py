"""Pure, bounded permission data for the DSH native bridge.

Only explicit known whole-tool Claude names in deny/ask lists translate. No
arguments, shell expressions, wildcard families or grants are approximated.
The collector must translate each original source before merging: merging
Claude settings first would erase repeated entries and their origin/index.

``blocked`` means the source has an unrepresentable restriction, an invalid
field, or an unknown permission field. Consumers must report every diagnostic
and refuse activation of that policy, not activate its partial translated data
as a complete policy. Allow-only diagnostics are nonblocking: no grant is
emitted and native defaults/presets stay untouched. An absent permissions key
needs no translation; an explicitly present invalid value must be diagnosed.

This module does not enforce policy. The bridge owns the final monotonic deny
guard and an ask waterfall preserving downstream deny/cancel/ask and sandbox
decisions. Runtime audit must require every mapped name, including read_image;
an unavailable tool must never be dropped to make activation succeed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypedDict

from ai_dotfiles.core.dsh_render import (
    DshDiagnostic,
    DshProvenance,
    native_tool_names,
)
from ai_dotfiles.core.manifest import DshPermissionMode

DSH_PERMISSION_GENERATOR_VERSION = 2
DSH_PERMISSION_SCHEMA_VERSION = 1
PermissionDecision = Literal["deny", "ask"]


class DshPermissionContributionData(TypedDict):
    decision: PermissionDecision
    entry: str
    nativeTools: list[str]
    field: str
    provenance: dict[str, str | int]


class DshPermissionGapData(TypedDict):
    value: object
    code: str
    origin: str
    element: str
    field: str
    reason: str
    blocking: bool
    provenance: dict[str, str | int]


class DshPermissionBridgeData(TypedDict):
    schemaVersion: int
    generator: int
    deny: list[str]
    ask: list[str]
    requiredTools: list[str]
    blocked: bool
    contributions: list[DshPermissionContributionData]
    diagnostics: list[DshPermissionGapData]


@dataclass(frozen=True)
class DshPermissionContribution:
    """One exact source entry; repeated entries/origins are never discarded."""

    decision: PermissionDecision
    entry: str
    native_tools: tuple[str, ...]
    field: str
    provenance: DshProvenance

    def as_dict(self) -> DshPermissionContributionData:
        """Return JSON bridge data with the original spelling and field index."""
        return {
            "decision": self.decision,
            "entry": self.entry,
            "nativeTools": list(self.native_tools),
            "field": self.field,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class DshPermissionGap:
    """A diagnostic paired with an independent snapshot of its source value.

    Malformed objects/lists retain their values too, rather than disappearing
    during validation. Input is already decoded JSON, optionally supplied as
    a read-only Mapping; no source files are read or rewritten here.
    """

    value: object
    diagnostic: DshDiagnostic
    provenance: DshProvenance

    def as_dict(self) -> DshPermissionGapData:
        """Return a reportable gap without sharing mutable source containers."""
        return {
            "value": _copy_value(self.value),
            "code": self.diagnostic.code,
            "origin": self.diagnostic.origin,
            "element": self.diagnostic.element,
            "field": self.diagnostic.field,
            "reason": self.diagnostic.reason,
            "blocking": self.diagnostic.blocking,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class DshPermissionPolicy:
    """Merged data, with deduplicated tool names and complete source records.

    Deny and ask remain independent even for overlapping tools: a bridge must
    retain the deny guard rather than treating ask as an overriding grant.
    Tool lists are sorted; source records retain collector and list order.
    """

    contributions: tuple[DshPermissionContribution, ...] = ()
    gaps: tuple[DshPermissionGap, ...] = ()

    @property
    def deny(self) -> tuple[str, ...]:
        """Return deterministic exact native names subject to final denial."""
        return self._names("deny")

    @property
    def ask(self) -> tuple[str, ...]:
        """Return deterministic names requiring native one-shot approval."""
        return self._names("ask")

    @property
    def required_tools(self) -> tuple[str, ...]:
        """Return every translated name for the required availability audit."""
        return tuple(sorted(set(self.deny) | set(self.ask)))

    @property
    def diagnostics(self) -> tuple[DshDiagnostic, ...]:
        """Return the shared diagnostic contract without dropping provenance."""
        return tuple(gap.diagnostic for gap in self.gaps)

    @property
    def blocked(self) -> bool:
        """Whether this policy must be reported and refused for activation."""
        return any(item.blocking for item in self.diagnostics)

    def bridge_data(self) -> DshPermissionBridgeData:
        """Return inspectable data; consumers must gate activation on blocked.

        No allow list or native preset is supplied. This is not a native DSH
        configuration fragment, and producing it proves no runtime readiness.
        schemaVersion identifies this JSON contract; generator tracks changed
        translations of unchanged sources. Consumers must reject an unknown
        schema version or malformed payload rather than substitute empty lists
        or enable unrestricted access. Source JSON parse errors belong to the
        collector and must likewise stop activation before translation.
        Bump the generator when unchanged sources would produce changed data.
        """
        return {
            "schemaVersion": DSH_PERMISSION_SCHEMA_VERSION,
            "generator": DSH_PERMISSION_GENERATOR_VERSION,
            "deny": list(self.deny),
            "ask": list(self.ask),
            "requiredTools": list(self.required_tools),
            "blocked": self.blocked,
            "contributions": [item.as_dict() for item in self.contributions],
            "diagnostics": [gap.as_dict() for gap in self.gaps],
        }

    def _names(self, decision: PermissionDecision) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    tool
                    for item in self.contributions
                    if item.decision == decision
                    for tool in item.native_tools
                }
            )
        )


def _copy_value(value: object) -> object:
    """Copy decoded JSON containers without mutating read-only source maps."""
    if isinstance(value, Mapping):
        return {key: _copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    return value


def _gap(
    provenance: DshProvenance,
    field: str,
    value: object,
    code: str,
    reason: str,
    *,
    blocking: bool = True,
) -> DshPermissionGap:
    return DshPermissionGap(
        _copy_value(value),
        DshDiagnostic(
            code, provenance.origin, provenance.element, field, reason, blocking
        ),
        provenance,
    )


def translate_permissions(
    permissions: object,
    *,
    provenance: DshProvenance,
    mode: DshPermissionMode = "strict",
) -> DshPermissionPolicy:
    """Translate one original source's permissions object without editing it.

    The caller supplies raw-source identity/hash, before any settings merge.
    Only an exact name accepted by native_tool_names is supported; whitespace
    is not stripped and Tool(argument), even Tool() or Tool(*), stays unmapped.
    Invalid source shapes and unknown fields get blocking diagnostics, while
    valid allow entries are retained as nonblocking unimplemented grants.
    Explicit native mode acknowledges only defaultMode="auto" as a reported
    translation gap. It never changes native permissions, presets or sandbox.
    """
    if not isinstance(permissions, Mapping):
        return DshPermissionPolicy(
            gaps=(
                _gap(
                    provenance,
                    "permissions",
                    permissions,
                    "INVALID_FIELD",
                    "permissions requires an object containing deny/ask/allow lists; "
                    "correct the source before activating its policy",
                ),
            )
        )
    contributions: list[DshPermissionContribution] = []
    gaps: list[DshPermissionGap] = []
    decisions: tuple[Literal["deny", "ask", "allow"], ...] = ("deny", "ask", "allow")
    for decision in decisions:
        if decision not in permissions:
            continue
        entries = permissions[decision]
        field = f"permissions.{decision}"
        if not isinstance(entries, list):
            gaps.append(
                _gap(
                    provenance,
                    field,
                    entries,
                    "INVALID_FIELD",
                    f"{field} requires a list of non-empty strings; "
                    "a scalar or null cannot be treated as an empty policy",
                )
            )
            continue
        for index, entry in enumerate(entries):
            entry_field = f"{field}[{index}]"
            if not isinstance(entry, str) or not entry.strip():
                gaps.append(
                    _gap(
                        provenance,
                        entry_field,
                        entry,
                        "INVALID_FIELD",
                        "Permission entries require non-empty strings; correct "
                        "the original entry before activating its policy",
                    )
                )
            elif decision == "allow":
                gaps.append(
                    _gap(
                        provenance,
                        entry_field,
                        entry,
                        "ALLOW_UNMAPPED",
                        "Claude allow grants are not translated; retain this "
                        "source grant for review without changing DSH's native "
                        "defaults, presets or sandbox decisions",
                        blocking=False,
                    )
                )
            else:
                native = native_tool_names(entry)
                if native is None:
                    gaps.append(
                        _gap(
                            provenance,
                            entry_field,
                            entry,
                            "PERMISSION_UNMAPPED",
                            "Only exact whole-tool names Read, Write, Edit, Glob, "
                            "Grep, Bash, WebFetch and WebSearch have a proven "
                            "mapping; arguments (including empty/all arguments), "
                            "expressions, wildcards and other names require "
                            "manual native policy review before activation",
                        )
                    )
                else:
                    contributions.append(
                        DshPermissionContribution(
                            decision, entry, native, entry_field, provenance
                        )
                    )
    for key, value in permissions.items():
        if key not in ("deny", "ask", "allow"):
            if key == "defaultMode" and value == "auto" and mode == "native":
                gaps.append(
                    _gap(
                        provenance,
                        "permissions['defaultMode']",
                        value,
                        "DEFAULT_MODE_NATIVE",
                        "Claude defaultMode=auto has no implemented native "
                        "equivalent; this source scope explicitly acknowledges "
                        "the limitation via dsh_permission_mode=native. DSH keeps "
                        "its existing permissions, presets and sandbox decisions",
                        blocking=False,
                    )
                )
                continue
            gaps.append(
                _gap(
                    provenance,
                    f"permissions[{key!r}]",
                    value,
                    "FIELD_UNMAPPED",
                    "This permission field has no implemented native equivalent; "
                    "review it explicitly instead of inferring a DSH preset or "
                    "ignoring a possible restriction",
                )
            )
    return DshPermissionPolicy(tuple(contributions), tuple(gaps))


def merge_permission_policies(
    policies: Iterable[DshPermissionPolicy],
) -> DshPermissionPolicy:
    """Combine original sources without deduplicating their diagnostic records.

    Restrictions accumulate across origins/scopes; native names are deduplicated
    only in the policy views. A blocking source remains blocking after merging.
    """
    contributions: list[DshPermissionContribution] = []
    gaps: list[DshPermissionGap] = []
    for policy in policies:
        contributions.extend(policy.contributions)
        gaps.extend(policy.gaps)
    return DshPermissionPolicy(tuple(contributions), tuple(gaps))
