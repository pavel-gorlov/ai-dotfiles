"""Pure DSH element data, grounded in the native 0.2.0-rc.2 contracts.

No files, profiles or runtime plugins are written here. Skills keep their whole
source directory; their Markdown is never shortened or rewritten. The shared
instruction body keeps Codex's existing normalization, while bridge text keeps
every source character. Child filters are exact known global tool names, not a
security boundary, and require a runtime availability audit before activation.

The project's small frontmatter parser cannot prove arbitrary YAML. DEFERRED
results are not native limitations or MANUAL migrations: consumers must parse
the unchanged source with the pinned native parser and call the renderer again
with ``native_frontmatter`` before installing/activating it. That argument is
already parsed JSON metadata, never guessed or evaluated YAML in Python.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Required, TypedDict

from ai_dotfiles.core.agents_md import rule_name_of
from ai_dotfiles.core.codex_render import source_sha256, split_body
from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.frontmatter import parse_frontmatter

DSH_RENDER_GENERATOR_VERSION = 1
DSH_SUBAGENT_PACKAGE = "@deepseek-ai/dsh-subagent"
DSH_SUBAGENT_SPAWN_PACKAGE = "@deepseek-ai/dsh-subagent-spawn-in-process"
DSH_SUBAGENT_TOOL_PACKAGE = "@deepseek-ai/dsh-tool-subagent"
DSH_AGENT_REQUIRED_PACKAGES = (
    DSH_SUBAGENT_PACKAGE,
    DSH_SUBAGENT_SPAWN_PACKAGE,
    DSH_SUBAGENT_TOOL_PACKAGE,
)

# Read includes image reading in Claude. Native read_image exists only with the
# attachments service; an audit must diagnose its absence, never drop it here.
CLAUDE_TOOL_NAMES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "Read": ("read", "read_image"),
        "Write": ("write",),
        "Edit": ("edit",),
        "Glob": ("glob",),
        "Grep": ("grep",),
        "Bash": ("bash",),
        "WebFetch": ("web_fetch",),
        "WebSearch": ("web_search",),
    }
)
_SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ELEMENT_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*\Z")
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")
_LIST_ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.+)$")
_YAML_NON_STRING_RE = re.compile(
    r"(?:true|false|null|~|[-+]?(?:[0-9][0-9_.eE+-]*|\.[0-9]+)|"
    r"[-+]?\.(?:inf|nan))\Z",
    re.IGNORECASE,
)
_LEGACY_INVOCATION = {
    "disableModelInvocation": "disable-model-invocation",
    "modelInvocable": "disable-model-invocation",
    "userInvocable": "user-invocable",
}
_SKILL_FIELDS = frozenset(
    {"name", "description", "whenToUse", "metadata", "depends"}
    | {"disable-model-invocation", "user-invocable"}
    | _LEGACY_INVOCATION.keys()
)
_SKILL_EXECUTION_FIELDS = frozenset(
    {"allowed-tools", "context", "agent", "hooks", "model"}
)


@dataclass(frozen=True)
class DshDiagnostic:
    """One gap with its origin (catalog/domain/local), element and source field.

    ``code`` is a stable machine label; ``reason`` is human-readable evidence.
    ``blocking`` prevents usable activation of the affected element. A
    STATIC_PARSE_UNSUPPORTED is deferred validation, not a native capability
    gap. Permission/hooks/config consumers may reuse this same field contract.
    """

    code: str
    origin: str
    element: str
    field: str
    reason: str
    blocking: bool = True


@dataclass(frozen=True)
class DshProvenance:
    """Source identity and raw UTF-8 digest, independent of rendered payload.

    ``origin`` is supplied by the collector, not inferred from a filesystem
    location. ``element`` is a stable source specifier, defaulting to its path.
    Bump the generator whenever unchanged sources would produce different data.
    These records do not themselves grant ownership of files or Cordis rows.
    """

    source: Path
    origin: str
    element: str
    source_sha256: str
    generator: int = DSH_RENDER_GENERATOR_VERSION

    def as_dict(self) -> dict[str, str | int]:
        """Return JSON-compatible drift metadata for registry consumers."""
        return {
            "source": str(self.source),
            "origin": self.origin,
            "element": self.element,
            "source_sha256": self.source_sha256,
            "generator": self.generator,
        }


@dataclass(frozen=True)
class DshRenderResult[T]:
    """READY payload, DEFERRED native validation, or MANUAL semantic gap.

    Only READY may activate. DEFERRED preserves source/provenance and must be
    retried with native-parsed metadata; MANUAL has no callable agent row.
    Nonblocking diagnostics (e.g. MODEL_UNMAPPED) still accompany READY data.
    """

    provenance: DshProvenance
    payload: T | None
    diagnostics: tuple[DshDiagnostic, ...] = ()
    status: Literal["READY", "DEFERRED", "MANUAL"] = "READY"


class DshSkillInvocation(TypedDict):
    modelInvocable: bool
    userInvocable: bool


@dataclass(frozen=True)
class DshSkillPayload:
    """The original bundle/flat source and proven native discovery metadata.

    DEFERRED keeps ``name``, ``description`` and ``invocation`` unset rather than
    falsely treating a YAML marker as description or permitting invocation.
    ``source_text`` and ``body`` preserve source whitespace; native filesystem
    loading itself trims a skill's loaded body, which this renderer does not.
    """

    source: Path
    directory: Path
    source_text: str
    body: str
    name: str | None
    description: str | None
    invocation: DshSkillInvocation | None


class DshAgentOptions(TypedDict, total=False):
    provider: str
    model: str
    reasoningEffort: str
    maxTokens: int


class DshToolFilter(TypedDict, total=False):
    allow: list[str]
    deny: list[str]


class DshSubagentConfig(TypedDict, total=False):
    provider: Required[str]
    toolName: Required[str]
    persona: Required[str]
    toolFilter: DshToolFilter
    agentOptions: DshAgentOptions


class DshSubagentRow(TypedDict):
    id: str
    name: str
    config: DshSubagentConfig


@dataclass(frozen=True)
class DshAgentPayload:
    """One stock spawn tool plus exact bridge data, never a cloned preset.

    ``required_tools`` includes both allow and deny names: the native service
    rejects unknown filter names at startup. Native Config has no description
    key; the bridge rewrites the tool schema and literal roster by ``toolName``.
    Only explicit native-fragment options enter ``agentOptions``. Omission
    inherits the parent's latest session route using native composition.
    """

    name: str
    description: str
    persona: str
    source_model: str | None
    row: DshSubagentRow
    required_tools: tuple[str, ...]

    def bridge_data(self, provenance: DshProvenance) -> dict[str, object]:
        """Return literal description/persona data for the generated bridge."""
        return {
            "name": self.name,
            "toolName": self.row["config"]["toolName"],
            "description": self.description,
            "persona": self.persona,
            "sourceModel": self.source_model,
            "provenance": provenance.as_dict(),
        }


@dataclass(frozen=True)
class DshRulePayload:
    """Shared marker body or private literal unconditional instruction.

    ``body`` is the existing Codex normalized body for shared blocks, exact
    source text for literal sections. ``literal_body`` always preserves the
    original body for provenance/bridge inspection. Paths never reach either.
    """

    name: str
    activation: Literal["shared", "literal"]
    body: str
    literal_body: str
    description: str | None

    def bridge_data(self, provenance: DshProvenance) -> dict[str, object]:
        """Return a private literal rule; shared blocks have no bridge row."""
        if self.activation != "literal":
            raise ElementError("Shared DSH rules belong in AGENTS.md, not the bridge")
        return {
            "name": self.name,
            "body": self.literal_body,
            "description": self.description,
            "provenance": provenance.as_dict(),
        }


def native_tool_names(claude_name: str) -> tuple[str, ...] | None:
    """Map only a proven whole-tool name, for child filters/policy/hooks.

    Task/Agent families, MCP names, wildcards, constrained argument patterns
    and already-native spellings are deliberately not guessed here.
    """
    return CLAUDE_TOOL_NAMES.get(claude_name)


def _read_source(
    source: Path, origin: str, element: str | None
) -> tuple[str, DshProvenance]:
    try:
        # read_text normalizes newlines; raw decoding preserves literal CRLF.
        text = source.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ElementError(f"Cannot read DSH {origin} source {source}: {exc}") from exc
    return text, DshProvenance(
        source, origin, element or str(source), source_sha256(text)
    )


def _diagnostic(
    provenance: DshProvenance,
    code: str,
    field: str,
    reason: str,
    *,
    blocking: bool = True,
) -> DshDiagnostic:
    return DshDiagnostic(
        code, provenance.origin, provenance.element, field, reason, blocking
    )


def _split_literal(text: str) -> tuple[str | None, str]:
    """Split only exact native delimiters, consuming no body whitespace."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None, text
    for index, line in enumerate(lines[1:], 1):
        if line.rstrip("\r\n") == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    return None, text


def _simple_scalar(raw: str) -> object:
    """Prove only the shared parser's simple scalar/JSON-string subset."""
    if not raw:
        return None
    if raw.startswith('"'):
        # JSON strings are a proven subset, including escaped quotes/newlines.
        value: object = json.loads(raw)
        if not isinstance(value, str):
            raise ValueError("not a string")
        return value
    if raw.startswith("'"):
        if not raw.endswith("'") or "'" in raw[1:-1]:
            raise ValueError("complex single-quoted scalar")
        return raw[1:-1]
    if (
        raw[0] in "|>{[&*!%@`"
        or ": " in raw
        or " #" in raw
        or _YAML_NON_STRING_RE.fullmatch(raw)
    ):
        raise ValueError("value needs native YAML parsing")
    return raw


def _metadata(
    text: str,
    provenance: DshProvenance,
    native_frontmatter: Mapping[str, object] | None,
) -> tuple[dict[str, object], str, list[DshDiagnostic], bool]:
    header, body = _split_literal(text)
    if native_frontmatter is not None:
        return dict(native_frontmatter), body, [], False
    if header is None:
        if text.split("\n", 1)[0].rstrip("\r") == "---":
            return (
                {},
                body,
                [
                    _diagnostic(
                        provenance,
                        "INVALID_FRONTMATTER",
                        "frontmatter",
                        "Opening frontmatter delimiter has no native closing delimiter",
                    )
                ],
                False,
            )
        return {}, body, [], False
    parsed: dict[str, object] = parse_frontmatter(f"---\n{header}\n---\n")
    diagnostics: list[DshDiagnostic] = []
    seen: set[str] = set()
    current = "frontmatter"
    list_field = False
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key_match = _KEY_RE.fullmatch(line)
        try:
            if key_match is not None:
                current, raw = key_match.groups()
                raw = raw.rstrip()
                if current in seen:
                    raise ValueError("duplicate field")
                seen.add(current)
                list_field = not raw
                if raw.startswith("[") and raw.endswith("]"):
                    inner = raw[1:-1]
                    items = inner.split(",") if inner.strip() else []
                    parsed[current] = [_simple_scalar(item.strip()) for item in items]
                elif not raw:
                    parsed[current] = None
                else:
                    # Invocation numeric/boolean spellings are native aliases.
                    if current in {
                        "disable-model-invocation",
                        "user-invocable",
                        "always_on",
                    } and raw.lower() in {"true", "false", "1", "0"}:
                        parsed[current] = raw
                        continue
                    parsed[current] = _simple_scalar(raw)
            elif list_field and (item_match := _LIST_ITEM_RE.fullmatch(line)):
                value = _simple_scalar(item_match.group(1).rstrip())
                existing = parsed.get(current)
                if existing is None:
                    parsed[current] = [value]
                elif isinstance(existing, list):
                    existing.append(value)
                else:
                    raise ValueError("unsupported block list")
            else:
                raise ValueError("multiline scalar or nested/unsupported YAML")
        except ValueError as exc:
            diagnostics.append(
                _diagnostic(
                    provenance,
                    "STATIC_PARSE_UNSUPPORTED",
                    current,
                    f"Cannot prove {current} with the simple parser ({exc}); "
                    "retain the source and validate with the pinned native YAML parser",
                )
            )
    return parsed, body, diagnostics, bool(diagnostics)


def _required_string(
    data: Mapping[str, object], field: str, provenance: DshProvenance
) -> tuple[str | None, list[DshDiagnostic]]:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        return None, [
            _diagnostic(
                provenance, "INVALID_FIELD", field, "A non-empty string is required"
            )
        ]
    return value, []


def _boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.lower() in {"true", "yes", "on", "1"}:
            return True
        if value.lower() in {"false", "no", "off", "0"}:
            return False
    return None


def validate_skill(
    source: Path,
    *,
    origin: str = "catalog",
    element: str | None = None,
    native_frontmatter: Mapping[str, object] | None = None,
) -> DshRenderResult[DshSkillPayload]:
    """Validate native discovery fields without any description length cap.

    Pass the instruction file, not the directory. Deferred payloads retain the
    source and bundle directory and may not activate until native validation.
    """
    text, provenance = _read_source(source, origin, element)
    data, body, diagnostics, deferred = _metadata(text, provenance, native_frontmatter)
    if deferred:
        payload = DshSkillPayload(source, source.parent, text, body, None, None, None)
        return DshRenderResult(provenance, payload, tuple(diagnostics), "DEFERRED")
    name, errors = _required_string(data, "name", provenance)
    diagnostics.extend(errors)
    description, errors = _required_string(data, "description", provenance)
    diagnostics.extend(errors)
    if name is not None and not _SKILL_NAME_RE.fullmatch(name):
        diagnostics.append(
            _diagnostic(
                provenance,
                "INVALID_FIELD",
                "name",
                "Native skill names require kebab-case: [a-z0-9]+(-[a-z0-9]+)*",
            )
        )
    for legacy, canonical in _LEGACY_INVOCATION.items():
        if legacy in data:
            diagnostics.append(
                _diagnostic(
                    provenance,
                    "INVALID_FIELD",
                    legacy,
                    f"Native DSH rejects this legacy key; use {canonical}",
                )
            )
    invocation: DshSkillInvocation = {"modelInvocable": True, "userInvocable": True}
    for field in ("disable-model-invocation", "user-invocable"):
        if field not in data:
            continue
        value = _boolean(data[field])
        if value is None:
            diagnostics.append(
                _diagnostic(
                    provenance,
                    "INVALID_FIELD",
                    field,
                    "Native invocation fields require a boolean or a supported "
                    "boolean spelling",
                )
            )
        elif field == "disable-model-invocation":
            invocation["modelInvocable"] = not value
        else:
            invocation["userInvocable"] = value
    for field in sorted(data.keys() - _SKILL_FIELDS):
        diagnostics.append(
            _diagnostic(
                provenance,
                "FIELD_UNMAPPED",
                field,
                "The native filesystem skill provider does not implement this field",
                blocking=field in _SKILL_EXECUTION_FIELDS,
            )
        )
    if any(item.blocking for item in diagnostics):
        return DshRenderResult(provenance, None, tuple(diagnostics), "MANUAL")
    payload = DshSkillPayload(
        source, source.parent, text, body, name, description, invocation
    )
    return DshRenderResult(provenance, payload, tuple(diagnostics))


def render_rule(
    source: Path,
    *,
    origin: str = "catalog",
    element: str | None = None,
    native_frontmatter: Mapping[str, object] | None = None,
) -> DshRenderResult[DshRulePayload]:
    """Keep no-path always-on rules shared and other no-path rules literal.

    Original paths are checked before Codex's classifier: even paths plus
    always_on or globs cannot widen DSH activation or infer an on-demand skill.
    """
    text, provenance = _read_source(source, origin, element)
    data, body, diagnostics, deferred = _metadata(text, provenance, native_frontmatter)
    if deferred:
        return DshRenderResult(provenance, None, tuple(diagnostics), "DEFERRED")
    paths = data.get("paths")
    if paths not in (None, [], ""):
        diagnostics.append(
            _diagnostic(
                provenance,
                "PATH_ACTIVATION_UNSUPPORTED",
                "paths",
                f"Original paths {paths!r} require Claude file/glob activation; "
                "native DSH directory/cwd/read instructions are not equivalent",
            )
        )
    if "paths" in data and not isinstance(paths, (list, str)):
        diagnostics.append(
            _diagnostic(
                provenance,
                "INVALID_FIELD",
                "paths",
                "paths requires a list or string; no activation was inferred",
            )
        )
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        diagnostics.append(
            _diagnostic(
                provenance,
                "INVALID_FIELD",
                "description",
                "description requires a string",
            )
        )
    for field in sorted(
        data.keys() - {"name", "description", "always_on", "paths", "depends"}
    ):
        diagnostics.append(
            _diagnostic(
                provenance,
                "FIELD_UNMAPPED",
                field,
                "Unknown rule activation metadata cannot become unconditional "
                "DSH instructions",
            )
        )
    if any(item.blocking for item in diagnostics):
        return DshRenderResult(provenance, None, tuple(diagnostics), "MANUAL")
    # Classification must agree with Codex's parser of the original source,
    # even after native YAML parses e.g. 1/1.0/comments into different types.
    # Native parsing validates fidelity; it must not add shared Codex blocks.
    always = parse_frontmatter(text).get("always_on")
    shared = always is True or (
        isinstance(always, str) and always.strip().lower() in {"true", "yes", "1"}
    )
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    payload = DshRulePayload(
        rule_name_of(source),
        "shared" if shared else "literal",
        split_body(normalized) if shared else body,
        body,
        description if isinstance(description, str) else None,
    )
    return DshRenderResult(provenance, payload)


def _child_filter(
    data: Mapping[str, object], provenance: DshProvenance
) -> tuple[DshToolFilter, list[DshDiagnostic]]:
    result: DshToolFilter = {}
    diagnostics: list[DshDiagnostic] = []
    for field, target in (("tools", "allow"), ("disallowedTools", "deny")):
        if field not in data:
            continue
        value = data[field]
        if isinstance(value, str) and value.strip():
            names: list[object] = [part.strip() for part in value.split(",")]
        elif isinstance(value, list):
            names = value
        else:
            diagnostics.append(
                _diagnostic(
                    provenance,
                    "INVALID_FIELD",
                    field,
                    "Tool restrictions require a non-empty comma-separated "
                    "string or list",
                )
            )
            continue
        mapped: list[str] = []
        for name in names:
            native = native_tool_names(name) if isinstance(name, str) else None
            if native is None:
                diagnostics.append(
                    _diagnostic(
                        provenance,
                        "TOOL_UNMAPPED",
                        field,
                        f"Restriction {name!r} has no proven exact native "
                        "global-tool mapping; the agent cannot be emitted "
                        "unrestricted",
                    )
                )
            else:
                for tool in native:
                    if tool not in mapped:
                        mapped.append(tool)
        if target == "allow":
            result["allow"] = mapped
        else:
            result["deny"] = mapped
    return result, diagnostics


def _native_options(
    options: Mapping[str, object] | None, provenance: DshProvenance
) -> tuple[DshAgentOptions, list[DshDiagnostic]]:
    result: DshAgentOptions = {}
    diagnostics: list[DshDiagnostic] = []
    if options is None:
        return result, diagnostics
    for field, value in options.items():
        valid = False
        if (
            field in {"provider", "model", "reasoningEffort"}
            and isinstance(value, str)
            and value
        ):
            valid = True
            if field == "provider":
                result["provider"] = value
            elif field == "model":
                result["model"] = value
            else:
                result["reasoningEffort"] = value
        elif (
            field == "maxTokens"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and 1 <= value <= 2**53 - 1
            and int(value) == value
        ):
            result["maxTokens"] = int(value)
            valid = True
        if not valid:
            diagnostics.append(
                _diagnostic(
                    provenance,
                    "INVALID_NATIVE_OPTIONS",
                    f"agentOptions.{field}",
                    "Only explicit native provider/model/reasoningEffort "
                    "strings and positive safe-integer maxTokens are supported",
                )
            )
    # Native composition resolves missing route fields from the provider or
    # current parent session; partial explicit options must retain that behavior.
    return result, diagnostics


def render_agent(
    source: Path,
    *,
    origin: str = "catalog",
    element: str | None = None,
    native_frontmatter: Mapping[str, object] | None = None,
    native_agent_options: Mapping[str, object] | None = None,
) -> DshRenderResult[DshAgentPayload]:
    """Render one logical agent tool, retaining literal text and restrictions.

    ``native_agent_options`` comes explicitly from native fragment data, not
    from splitting a Claude model string. Omitted fields retain native parent/
    provider inheritance and effective-route preflight. Global/project contributions
    share an id; the collector merges global then project before insertion and
    refuses user row/tool collisions. This renderer never selects a profile.
    """
    text, provenance = _read_source(source, origin, element)
    data, body, diagnostics, deferred = _metadata(text, provenance, native_frontmatter)
    if deferred:
        return DshRenderResult(provenance, None, tuple(diagnostics), "DEFERRED")
    name, errors = _required_string(data, "name", provenance)
    diagnostics.extend(errors)
    description, errors = _required_string(data, "description", provenance)
    diagnostics.extend(errors)
    if name is not None and not _ELEMENT_NAME_RE.fullmatch(name):
        diagnostics.append(
            _diagnostic(
                provenance,
                "INVALID_FIELD",
                "name",
                "Managed agent names require an element-safe identifier",
            )
        )
    filters, errors = _child_filter(data, provenance)
    diagnostics.extend(errors)
    options, errors = _native_options(native_agent_options, provenance)
    diagnostics.extend(errors)
    model = data.get("model")
    if "model" in data and (not isinstance(model, str) or not model):
        diagnostics.append(
            _diagnostic(
                provenance,
                "INVALID_FIELD",
                "model",
                "model requires a non-empty string",
            )
        )
    elif isinstance(model, str) and model != "inherit":
        diagnostics.append(
            _diagnostic(
                provenance,
                "MODEL_UNMAPPED",
                "model",
                f"Claude model {model!r} is retained as provenance, not a native "
                "route; inherit the current parent session route unless "
                "explicit native fragment options supply it",
                blocking=False,
            )
        )
    for field in sorted(
        data.keys()
        - {
            "name",
            "description",
            "tools",
            "disallowedTools",
            "model",
            "depends",
        }
    ):
        diagnostics.append(
            _diagnostic(
                provenance,
                "FIELD_UNMAPPED",
                field,
                "This Claude agent field has no implemented native subagent equivalent",
                blocking=field != "color",
            )
        )
    if any(item.blocking for item in diagnostics):
        return DshRenderResult(provenance, None, tuple(diagnostics), "MANUAL")
    assert name is not None and description is not None
    config: DshSubagentConfig = {
        "provider": "spawn",
        "toolName": f"ai_dotfiles_agent_{name}",
        "persona": body,
    }
    if filters:
        config["toolFilter"] = filters
    if options:
        config["agentOptions"] = options
    row: DshSubagentRow = {
        "id": f"ai-dotfiles-agent-{name}",
        "name": DSH_SUBAGENT_TOOL_PACKAGE,
        "config": config,
    }
    required = tuple(
        dict.fromkeys([*filters.get("allow", []), *filters.get("deny", [])])
    )
    payload = DshAgentPayload(
        name,
        description,
        body,
        model if isinstance(model, str) else None,
        row,
        required,
    )
    return DshRenderResult(provenance, payload, tuple(diagnostics))
