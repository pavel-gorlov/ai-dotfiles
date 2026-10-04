"""DSH source fidelity, native metadata and fail-closed element contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_dotfiles.core.codex_render import split_body
from ai_dotfiles.core.dsh_render import (
    CLAUDE_TOOL_NAMES,
    DSH_AGENT_REQUIRED_PACKAGES,
    DSH_RENDER_GENERATOR_VERSION,
    DSH_SUBAGENT_TOOL_PACKAGE,
    native_tool_names,
    render_agent,
    render_rule,
    validate_skill,
)
from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.rule_classify import RuleClass, classify_rule


def _source(tmp_path: Path, header: str, body: str = "\n{{literal}}  \n\n") -> Path:
    source = tmp_path / "example.md"
    text = f"---\n{header}\n---\n{body}"
    source.write_bytes(text.encode("utf-8"))
    return source


def _skill(
    tmp_path: Path, extra: str = "", description: str = "A full description."
) -> Path:
    return _source(tmp_path, f"name: example\ndescription: {description}\n{extra}")


def _agent(tmp_path: Path, extra: str = "") -> Path:
    return _source(tmp_path, f"name: example\ndescription: An agent.\n{extra}")


def test_skill_preserves_full_directory_text_description_and_no_cap(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "example"
    directory.mkdir()
    source = directory / "SKILL.md"
    description = "  Use {{ untouched }}. Second sentence. " + "x" * 2048 + "  "
    body = "\r\n  # Body\r\n{{value}}  \r\n\r\n"
    text = (
        f"---\r\nname: example\r\ndescription: {json.dumps(description)}\r\n"
        f"---\r\n{body}"
    )
    source.write_bytes(text.encode("utf-8"))
    resource = directory / "script.sh"
    resource.write_text("exit 0\n", encoding="utf-8")
    result = validate_skill(source, origin="domain:@example", element="skill:example")
    assert result.status == "READY" and result.payload is not None
    assert result.payload.directory == directory
    assert result.payload.source_text == text
    assert result.payload.body == body
    assert result.payload.description == description
    assert result.payload.invocation == {"modelInvocable": True, "userInvocable": True}
    assert result.provenance.as_dict() == {
        "source": str(source),
        "origin": "domain:@example",
        "element": "skill:example",
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "generator": DSH_RENDER_GENERATOR_VERSION,
    }
    assert resource.read_text(encoding="utf-8") == "exit 0\n"


@pytest.mark.parametrize("name", ["a", "1", "a-1", "long-" + "a" * 100])
def test_native_skill_name_grammar_has_no_invented_length_cap(
    tmp_path: Path, name: str
) -> None:
    source = _source(tmp_path, f'name: "{name}"\ndescription: x')
    assert validate_skill(source).status == "READY"


@pytest.mark.parametrize("name", ["UPPER", "with_under", "a--b", "-a", "a-", "a b", ""])
def test_invalid_native_skill_names_are_diagnosed(tmp_path: Path, name: str) -> None:
    result = validate_skill(
        _source(tmp_path, f"name: {json.dumps(name)}\ndescription: x")
    )
    assert result.status == "MANUAL" and result.payload is None
    assert any(
        item.field == "name" and item.code == "INVALID_FIELD"
        for item in result.diagnostics
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("YES", True),
        ("on", True),
        ("1", True),
        ("false", False),
        ("NO", False),
        ("off", False),
        ("0", False),
        ('"TrUe"', True),
    ],
)
@pytest.mark.parametrize("field", ["disable-model-invocation", "user-invocable"])
def test_native_invocation_boolean_aliases(
    tmp_path: Path, raw: str, expected: bool, field: str
) -> None:
    result = validate_skill(_skill(tmp_path, f"{field}: {raw}"))
    assert result.status == "READY" and result.payload is not None
    assert result.payload.invocation is not None
    if field == "disable-model-invocation":
        assert result.payload.invocation["modelInvocable"] is not expected
        assert result.payload.invocation["userInvocable"] is True
    else:
        assert result.payload.invocation["userInvocable"] is expected
        assert result.payload.invocation["modelInvocable"] is True


@pytest.mark.parametrize("raw", ['" true "', "maybe", "[]", "{}", "null", "2"])
def test_invocation_never_defaults_open_after_invalid_or_unproven_value(
    tmp_path: Path, raw: str
) -> None:
    result = validate_skill(_skill(tmp_path, f"user-invocable: {raw}"))
    assert result.status != "READY"
    if result.payload is not None:
        assert result.status == "DEFERRED" and result.payload.invocation is None
    assert any(item.field == "user-invocable" for item in result.diagnostics)


@pytest.mark.parametrize(
    "field", ["disableModelInvocation", "modelInvocable", "userInvocable"]
)
def test_native_rejects_legacy_invocation_keys(tmp_path: Path, field: str) -> None:
    result = validate_skill(_skill(tmp_path, f'{field}: "true"'))
    assert result.status == "MANUAL" and result.payload is None
    assert any(
        item.field == field and "legacy" in item.reason for item in result.diagnostics
    )


@pytest.mark.parametrize(
    "header", ["", "name: example", "description: x", 'name: example\ndescription: ""']
)
def test_skill_required_metadata(tmp_path: Path, header: str) -> None:
    result = validate_skill(_source(tmp_path, header))
    assert result.status == "MANUAL" and result.payload is None
    assert result.diagnostics


@pytest.mark.parametrize(
    "description",
    [
        ">\n  Folded {{name}}.\n  Another sentence.",
        "|\n  Literal {{name}}.\n",
        r'"YAML \e escape"',
    ],
)
def test_valid_native_yaml_is_deferred_and_can_retry_with_literal_values(
    tmp_path: Path, description: str
) -> None:
    source = _skill(tmp_path, 'user-invocable: "false"', description)
    deferred = validate_skill(source, origin="local", element="skill:example")
    assert deferred.status == "DEFERRED" and deferred.payload is not None
    assert deferred.payload.description is None and deferred.payload.invocation is None
    assert deferred.payload.directory == source.parent
    assert all(item.code == "STATIC_PARSE_UNSUPPORTED" for item in deferred.diagnostics)
    semantic = "  Real {{name}}.\nEscaped \x1b value.  \n"
    ready = validate_skill(
        source,
        origin="local",
        element="skill:example",
        native_frontmatter={
            "name": "example",
            "description": semantic,
            "disable-model-invocation": True,
            "user-invocable": False,
            "metadata": {"nested": {"value": 1}},
        },
    )
    assert ready.status == "READY" and ready.payload is not None
    assert ready.payload.description == semantic
    assert ready.payload.invocation == {"modelInvocable": False, "userInvocable": False}
    assert ready.payload.source_text == deferred.payload.source_text
    assert ready.provenance == deferred.provenance


@pytest.mark.parametrize("value", [None, [], {}, True, 1])
def test_native_parsed_invalid_description_is_not_a_literal_marker(
    tmp_path: Path, value: object
) -> None:
    result = validate_skill(
        _skill(tmp_path), native_frontmatter={"name": "example", "description": value}
    )
    assert result.status == "MANUAL" and result.payload is None
    assert result.diagnostics[0].field == "description"


def test_native_invocation_metadata_has_the_same_strict_grammar(tmp_path: Path) -> None:
    source = _skill(tmp_path)
    for value in (True, "YES", 1, 1.0):
        result = validate_skill(
            source,
            native_frontmatter={
                "name": "example",
                "description": "x",
                "disable-model-invocation": value,
            },
        )
        assert result.payload is not None and result.payload.invocation is not None
        assert result.payload.invocation["modelInvocable"] is False
    invalid = validate_skill(
        source,
        native_frontmatter={
            "name": "example",
            "description": "x",
            "user-invocable": {"enabled": True},
        },
    )
    assert invalid.status == "MANUAL" and invalid.payload is None


def test_execution_restrictions_on_native_skills_are_not_silently_ignored(
    tmp_path: Path,
) -> None:
    result = validate_skill(_skill(tmp_path, "allowed-tools: Read"))
    assert result.status == "MANUAL" and result.payload is None
    assert result.diagnostics[0].field == "allowed-tools"


def test_unmapped_passive_skill_fields_remain_in_unchanged_source(
    tmp_path: Path,
) -> None:
    source = _skill(tmp_path, "argument-hint: name")
    result = validate_skill(source)
    assert result.status == "READY" and result.payload is not None
    assert result.diagnostics[0].field == "argument-hint"
    assert not result.diagnostics[0].blocking
    assert "argument-hint: name" in result.payload.source_text


def test_json_escaped_description_is_literal_without_yaml_evaluator(
    tmp_path: Path,
) -> None:
    description = '  {{ value }} "quote" \\ backslash\nnewline\tend  '
    result = validate_skill(_skill(tmp_path, description=json.dumps(description)))
    assert result.status == "READY" and result.payload is not None
    assert result.payload.description == description


@pytest.mark.parametrize(
    "header",
    [
        "description: >\n  folded",
        "metadata:\n  nested: value",
        "description: x\ndescription: y",
        "description: x # comment",
        "description: 'It''s literal'",
    ],
)
def test_static_parser_limits_do_not_report_native_limitations(
    tmp_path: Path, header: str
) -> None:
    result = validate_skill(_source(tmp_path, f"name: example\n{header}"))
    assert result.status == "DEFERRED" and result.payload is not None
    assert all(item.code == "STATIC_PARSE_UNSUPPORTED" for item in result.diagnostics)


def test_always_on_rule_keeps_existing_shared_body_contract(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        'description: "  {{ trigger }}  "\nalways_on: true',
        "\n  {{ body }}  \n\n",
    )
    result = render_rule(source)
    assert result.status == "READY" and result.payload is not None
    assert result.payload.activation == "shared"
    assert result.payload.body == split_body(source.read_text(encoding="utf-8"))
    assert result.payload.literal_body == "\n  {{ body }}  \n\n"
    assert classify_rule(source) is RuleClass.ALWAYS_ON
    with pytest.raises(ElementError, match="AGENTS.md"):
        result.payload.bridge_data(result.provenance)


@pytest.mark.parametrize(
    "header",
    ["description: x", "description: x\nalways_on: false", "always_on: on", ""],
)
def test_no_path_description_rules_are_private_literal_unconditional_sections(
    tmp_path: Path, header: str
) -> None:
    body = "\n\t{{ never_interpolate }}  \n\n"
    result = render_rule(_source(tmp_path, header, body))
    assert result.status == "READY" and result.payload is not None
    assert result.payload.activation == "literal"
    assert result.payload.body == body
    assert result.payload.bridge_data(result.provenance)["body"] == body
    assert "skill" not in result.payload.bridge_data(result.provenance)


def test_rule_without_frontmatter_keeps_all_literal_text(tmp_path: Path) -> None:
    source = tmp_path / "rule.md"
    source.write_bytes(b"\r\n # Body\r\n{{raw}}  \r\n")
    result = render_rule(source)
    assert result.payload is not None and result.payload.activation == "literal"
    assert result.payload.body == "\r\n # Body\r\n{{raw}}  \r\n"


@pytest.mark.parametrize(
    "paths", ['["src"]', '["**/*.py"]', '["src", "**/*.py"]', '"src"', '[""]']
)
@pytest.mark.parametrize("always", ["true", "false"])
def test_all_original_nonempty_paths_are_manual_before_codex_classification(
    tmp_path: Path, paths: str, always: str
) -> None:
    source = _source(tmp_path, f"paths: {paths}\nalways_on: {always}")
    result = render_rule(source, origin="domain:@python", element="rule:example")
    assert result.status == "MANUAL" and result.payload is None
    gap = result.diagnostics[0]
    assert gap.code == "PATH_ACTIVATION_UNSUPPORTED" and gap.field == "paths"
    assert gap.origin == "domain:@python" and gap.element == "rule:example"
    assert "directory/cwd/read" in gap.reason
    if "**" in paths and always == "true":
        assert classify_rule(source) is RuleClass.ALWAYS_ON


def test_empty_paths_list_is_shared_but_nested_yaml_needs_native_parse(
    tmp_path: Path,
) -> None:
    ready = render_rule(_source(tmp_path, "paths: []\nalways_on: true"))
    assert ready.payload is not None and ready.payload.activation == "shared"
    source = _source(tmp_path, "paths:\n  include: src\nalways_on: true")
    deferred = render_rule(source)
    assert deferred.status == "DEFERRED" and deferred.payload is None
    manual = render_rule(
        source, native_frontmatter={"paths": {"include": "src"}, "always_on": True}
    )
    assert manual.status == "MANUAL" and manual.payload is None


def test_rule_native_retry_preserves_real_description_and_body(tmp_path: Path) -> None:
    source = _source(tmp_path, "description: >\n  description {{rule}}")
    deferred = render_rule(source)
    assert deferred.status == "DEFERRED"
    semantic = "description {{rule}}\n"
    ready = render_rule(source, native_frontmatter={"description": semantic})
    assert ready.payload is not None and ready.payload.description == semantic
    assert ready.payload.activation == "literal"
    assert ready.provenance == deferred.provenance


@pytest.mark.parametrize(
    ("source_value", "native_value", "activation"),
    [
        ("1", 1, "shared"),
        ("1.0", 1, "literal"),
        ("true # comment", True, "literal"),
        ("yes", "yes", "shared"),
        ("on", "on", "literal"),
    ],
)
def test_rule_retry_keeps_unchanged_codex_source_classification(
    tmp_path: Path, source_value: str, native_value: object, activation: str
) -> None:
    source = _source(
        tmp_path,
        f"description: >\n  Complex {{rule}}\nalways_on: {source_value}",
    )
    assert render_rule(source).status == "DEFERRED"
    ready = render_rule(
        source,
        native_frontmatter={
            "description": "Complex {rule}\n",
            "always_on": native_value,
        },
    )
    assert ready.payload is not None and ready.payload.activation == activation
    assert (classify_rule(source) is RuleClass.ALWAYS_ON) == (activation == "shared")


def test_exact_tool_mapping_and_conditional_images_are_shared_public_data() -> None:
    assert dict(CLAUDE_TOOL_NAMES) == {
        "Read": ("read", "read_image"),
        "Write": ("write",),
        "Edit": ("edit",),
        "Glob": ("glob",),
        "Grep": ("grep",),
        "Bash": ("bash",),
        "WebFetch": ("web_fetch",),
        "WebSearch": ("web_search",),
    }
    assert native_tool_names("Read") == ("read", "read_image")
    for name in ("Task", "Agent", "read", "*", "Read(*)", "mcp__server__tool"):
        assert native_tool_names(name) is None


def test_agent_emits_one_stock_named_row_literal_bridge_and_exact_filters(
    tmp_path: Path,
) -> None:
    description = '  Review {{sources}}. "Literal" description.  '
    body = "\r\n  You are {{ not_a_variable }}.  \r\n\r\n"
    source = _source(
        tmp_path,
        f"name: reviewer\ndescription: {json.dumps(description)}\n"
        "tools: [Read, Glob, Grep, Bash, Read]\ndisallowedTools: Edit, Write",
        body,
    )
    result = render_agent(source, origin="local", element="agent:reviewer")
    assert result.status == "READY" and result.payload is not None
    payload = result.payload
    assert payload.row == {
        "id": "ai-dotfiles-agent-reviewer",
        "name": DSH_SUBAGENT_TOOL_PACKAGE,
        "config": {
            "provider": "spawn",
            "toolName": "ai_dotfiles_agent_reviewer",
            "persona": body,
            "toolFilter": {
                "allow": ["read", "read_image", "glob", "grep", "bash"],
                "deny": ["edit", "write"],
            },
        },
    }
    assert payload.required_tools == (
        "read",
        "read_image",
        "glob",
        "grep",
        "bash",
        "edit",
        "write",
    )
    assert DSH_AGENT_REQUIRED_PACKAGES[-1] == payload.row["name"]
    assert "description" not in payload.row["config"]
    bridge = json.loads(json.dumps(payload.bridge_data(result.provenance)))
    assert bridge["description"] == description and bridge["persona"] == body
    assert bridge["provenance"]["origin"] == "local"


def test_block_tool_lists_and_empty_allow_are_faithful(tmp_path: Path) -> None:
    result = render_agent(
        _agent(tmp_path, "tools:\n  - Read\n  - WebFetch\ndisallowedTools:\n  - Bash")
    )
    assert result.payload is not None
    assert result.payload.row["config"]["toolFilter"] == {
        "allow": ["read", "read_image", "web_fetch"],
        "deny": ["bash"],
    }
    empty = render_agent(_agent(tmp_path, "tools: []\ndisallowedTools: []"))
    assert empty.payload is not None
    assert empty.payload.row["config"]["toolFilter"] == {"allow": [], "deny": []}
    omitted = render_agent(_agent(tmp_path))
    assert (
        omitted.payload is not None
        and "toolFilter" not in omitted.payload.row["config"]
    )


@pytest.mark.parametrize(
    "restriction",
    [
        "Task",
        "Agent",
        "Task(worker)",
        "mcp__x__read",
        "Read(*)",
        "Unknown",
        "*",
        "MultiEdit",
        "read",
    ],
)
@pytest.mark.parametrize("field", ["tools", "disallowedTools"])
def test_unrepresentable_restrictions_never_emit_callable_or_unrestricted_agents(
    tmp_path: Path, restriction: str, field: str
) -> None:
    result = render_agent(
        _agent(tmp_path, f"{field}: Read, {restriction}"),
        origin="local",
        element="agent:example",
    )
    assert result.status == "MANUAL" and result.payload is None
    assert any(
        item.code == "TOOL_UNMAPPED"
        and item.field == field
        and item.origin == "local"
        and item.element == "agent:example"
        for item in result.diagnostics
    )


@pytest.mark.parametrize(
    "model",
    [
        None,
        "inherit",
        "sonnet",
        "opus",
        "haiku",
        "claude-sonnet-4-6",
        "deepseek/arbitrary/model",
        "future-provider:future-model",
    ],
)
def test_claude_models_never_invent_native_routes(
    tmp_path: Path, model: str | None
) -> None:
    result = render_agent(_agent(tmp_path, f"model: {model}" if model else ""))
    assert result.status == "READY" and result.payload is not None
    assert result.payload.source_model == model
    assert "agentOptions" not in result.payload.row["config"]
    assert [item.code for item in result.diagnostics] == (
        [] if model in (None, "inherit") else ["MODEL_UNMAPPED"]
    )
    assert all(not item.blocking for item in result.diagnostics)


def test_explicit_native_route_comes_from_fragment_data_without_splitting_model(
    tmp_path: Path,
) -> None:
    options = {
        "provider": "custom-provider",
        "model": "opaque/model:id",
        "reasoningEffort": "provider-owned",
        "maxTokens": 1024,
    }
    result = render_agent(
        _agent(tmp_path, "model: sonnet"), native_agent_options=options
    )
    assert result.payload is not None
    assert result.payload.row["config"]["agentOptions"] == options
    assert result.payload.row["config"]["provider"] == "spawn"
    assert result.payload.source_model == "sonnet"
    assert result.diagnostics[0].code == "MODEL_UNMAPPED"


@pytest.mark.parametrize(
    "options",
    [
        {"provider": "", "model": "model"},
        {"reasoningEffort": ""},
        {"maxTokens": 0},
        {"maxTokens": True},
        {"maxTokens": 2**53},
        {"maxTokens": 7.25},
        {"maxTokens": float("nan")},
        {"maxTokens": float("inf")},
        {"arbitrary": "x"},
    ],
)
def test_invalid_native_options_are_manual_without_guessed_route(
    tmp_path: Path, options: dict[str, object]
) -> None:
    result = render_agent(_agent(tmp_path), native_agent_options=options)
    assert result.status == "MANUAL" and result.payload is None
    assert all(item.code == "INVALID_NATIVE_OPTIONS" for item in result.diagnostics)


@pytest.mark.parametrize(
    "options",
    [
        {"provider": "explicit-provider"},
        {"model": "opaque/model:id"},
        {"reasoningEffort": "provider-owned"},
        {"maxTokens": 100},
        {"maxTokens": 7.0},
        {"reasoningEffort": "provider-owned", "maxTokens": 100},
    ],
)
def test_partial_native_options_preserve_omitted_field_inheritance(
    tmp_path: Path, options: dict[str, object]
) -> None:
    result = render_agent(
        _agent(tmp_path, "model: sonnet"), native_agent_options=options
    )
    assert result.status == "READY" and result.payload is not None
    config = result.payload.row["config"]
    assert config["agentOptions"] == options
    assert set(config["agentOptions"]) == set(options)
    if "maxTokens" in options:
        assert type(config["agentOptions"]["maxTokens"]) is int
    assert config["provider"] == "spawn"
    assert result.payload.source_model == "sonnet"
    assert [item.code for item in result.diagnostics] == ["MODEL_UNMAPPED"]


def test_logical_names_are_injective_and_same_across_scope_for_merge(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, "name: review-team\ndescription: x")
    global_result = render_agent(source, origin="global")
    project_result = render_agent(source, origin="project")
    second = render_agent(_source(tmp_path, "name: review_team\ndescription: x"))
    assert (
        global_result.payload is not None
        and project_result.payload is not None
        and second.payload is not None
    )
    assert global_result.payload.row == project_result.payload.row
    assert global_result.payload.row["id"] != second.payload.row["id"]
    assert (
        global_result.payload.row["config"]["toolName"]
        != second.payload.row["config"]["toolName"]
    )


def test_agent_native_retry_preserves_literal_description_and_filters(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path,
        "name: example\ndescription: |\n  {{agent}}\nmodel: opus\ntools: [Read]",
    )
    deferred = render_agent(source)
    assert deferred.status == "DEFERRED" and deferred.payload is None
    ready = render_agent(
        source,
        native_frontmatter={
            "name": "example",
            "description": "  {{agent}}\n",
            "model": "opus",
            "tools": ["Read"],
        },
    )
    assert ready.status == "READY" and ready.payload is not None
    assert ready.provenance == deferred.provenance
    assert ready.payload.description == "  {{agent}}\n"
    assert ready.payload.row["config"]["toolFilter"]["allow"] == ["read", "read_image"]
    assert "agentOptions" not in ready.payload.row["config"]
    assert ready.diagnostics[0].code == "MODEL_UNMAPPED"


@pytest.mark.parametrize(
    "extra",
    [
        "permissionMode: bypassPermissions",
        "memory: project",
        "skills: [example]",
        "isolation: worktree",
        "future-restriction: true",
    ],
)
def test_unmapped_agent_runtime_semantics_cannot_be_silently_dropped(
    tmp_path: Path, extra: str
) -> None:
    result = render_agent(
        _agent(tmp_path, extra),
        native_frontmatter={
            "name": "example",
            "description": "x",
            extra.split(":", 1)[0]: "value",
        },
    )
    assert result.status == "MANUAL" and result.payload is None
    assert result.diagnostics[0].code == "FIELD_UNMAPPED"


@pytest.mark.parametrize("renderer", [validate_skill, render_agent, render_rule])
def test_unreadable_source_raises_core_error_with_origin(
    tmp_path: Path, renderer: object
) -> None:
    # Separate parametrized callables keep the failure contract shared.
    assert callable(renderer)
    with pytest.raises(ElementError, match="local.*missing.md"):
        renderer(tmp_path / "missing.md", origin="local")


@pytest.mark.parametrize("renderer", [validate_skill, render_agent, render_rule])
def test_unclosed_frontmatter_never_activates(tmp_path: Path, renderer: object) -> None:
    assert callable(renderer)
    source = tmp_path / "broken.md"
    source.write_text("---\nname: x\ndescription: x\n", encoding="utf-8")
    result = renderer(source)
    assert result.status == "MANUAL" and result.payload is None
    assert any(item.code == "INVALID_FRONTMATTER" for item in result.diagnostics)


def test_source_and_generator_provenance_change_without_rewriting_source(
    tmp_path: Path,
) -> None:
    source = _agent(tmp_path)
    before = source.read_bytes()
    first = render_agent(source)
    assert source.read_bytes() == before
    assert first == render_agent(source)
    source.write_bytes(before + b"\nchanged\n")
    second = render_agent(source)
    assert first.provenance.source_sha256 != second.provenance.source_sha256
    assert (
        first.provenance.generator
        == second.provenance.generator
        == DSH_RENDER_GENERATOR_VERSION
    )
