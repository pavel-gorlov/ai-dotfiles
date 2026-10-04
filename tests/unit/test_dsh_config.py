"""Exact source/environment/MCP contracts, without launching native services."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from ai_dotfiles.core.dsh_config import (
    validate_native_fragment,
)
from ai_dotfiles.core.dsh_native import (
    DshNativeRuntime,
    invoke_native,
)
from ai_dotfiles.core.errors import ConfigError, ExternalError


@pytest.fixture(autouse=True)
def mock_shipped_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subprocess contract tests do not read packaged files."""
    monkeypatch.setattr(
        "ai_dotfiles.core.dsh_native.compose_module_text", lambda: "/* helper */"
    )


def test_native_paths_are_bound_and_all_nonpath_strings_are_exact(
    tmp_path: Path,
) -> None:
    data = [
        {
            "insert": [
                {
                    "id": "plugin",
                    "name": "./plugins/plugin.mjs",
                    "config": {
                        "persona": "./literal {{ x }}",
                        "args": ["./literal"],
                        "metadata": {"constructor": "allowed"},
                    },
                },
                {
                    "id": "include",
                    "name": "cordis:include",
                    "config": {"path": "./entries.json"},
                },
                {
                    "id": "skills",
                    "name": "@deepseek-ai/dsh-skill-filesystem",
                    "config": {"customSkillDirs": ["./skills"], "watch": False},
                },
            ]
        }
    ]
    result = validate_native_fragment(
        data, source=tmp_path / "dsh.fragment.json", binding_root=tmp_path / "installed"
    )
    assert (
        result[0]["insert"][0]["name"]
        == (tmp_path / "installed/plugins/plugin.mjs").as_uri()
    )
    assert result[0]["insert"][0]["config"] == data[0]["insert"][0]["config"]
    assert (
        result[0]["insert"][1]["config"]["path"]
        == (tmp_path / "installed/entries.json").as_uri()
    )
    assert result[0]["insert"][2]["config"]["customSkillDirs"] == [
        str(tmp_path / "installed/skills")
    ]
    assert data[0]["insert"][0]["name"].startswith("./")


@pytest.mark.parametrize(
    "data",
    [
        {},
        [None],
        [{"config": {}}],
        [{"insert": [{"name": "x", "config": {"a": {"__jsExpr": "process.exit()"}}}]}],
        [{"insert": [{"name": "../outside.mjs"}]}],
        [{"insert": [{"name": "custom", "config": {"path": "./unproven"}}]}],
    ],
)
def test_invalid_or_unprovable_native_fragment_refuses(
    tmp_path: Path, data: object
) -> None:
    with pytest.raises(ConfigError):
        validate_native_fragment(
            data, source=tmp_path / "dsh.fragment.json", binding_root=tmp_path
        )


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        "{}",
        '{"schemaVersion":2,"ok":true,"result":{},"diagnostics":[]}',
        '{"schemaVersion":true,"ok":true,"result":{},"diagnostics":[]}',
        '{"schemaVersion":1,"ok":"true","result":{},"diagnostics":[]}',
        '{"schemaVersion":1,"ok":true,"result":[],"diagnostics":[]}',
        '{"schemaVersion":1,"ok":true,"result":{},"diagnostics":[{}]}',
        '{"schemaVersion":1,"ok":false,"result":{},"diagnostics":[]}',
    ],
)
def test_native_response_schema_and_failure_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response: str
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([], 0, response, "")),
    )
    runtime = DshNativeRuntime(tmp_path, Path("/node"), tmp_path / "bin.js")
    with pytest.raises(ConfigError):
        invoke_native(runtime, {}, cwd=tmp_path, env={})


def test_native_no_shell_and_env_forwarding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, '{"schemaVersion":1,"ok":true,"result":{},"diagnostics":[]}', ""
        )
    )
    monkeypatch.setattr(subprocess, "run", run)
    runtime = DshNativeRuntime(tmp_path, Path("/node"), tmp_path / "bin.js")
    invoke_native(
        runtime, {"literal": "$(no); bad"}, cwd=tmp_path, env={"A": "explicit"}
    )
    args, kwargs = run.call_args
    assert args[0][0] == "/node"
    assert "shell" not in kwargs
    assert kwargs["env"] == {"A": "explicit"}
    assert json.loads(kwargs["input"])["literal"] == "$(no); bad"


def test_native_subprocess_failure_is_external_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=OSError("cannot execute")))
    with pytest.raises(ExternalError):
        invoke_native(
            DshNativeRuntime(tmp_path, Path("/node"), tmp_path / "bin.js"),
            {},
            cwd=tmp_path,
            env={},
        )


def test_include_initial_and_nested_patches_bind_only_known_paths(
    tmp_path: Path,
) -> None:
    row = {
        "name": "cordis:include",
        "config": {
            "path": "./entries.json",
            "initial": [{"name": "./first.mjs", "config": {"persona": "./literal"}}],
            "patches": [{"insert": [{"name": "./second.mjs"}]}],
        },
    }
    result = validate_native_fragment(
        [{"insert": [row]}], source=tmp_path / "source.json", binding_root=tmp_path
    )
    config = result[0]["insert"][0]["config"]
    assert config["path"] == (tmp_path / "entries.json").as_uri()
    first = config["initial"][0]
    second = config["patches"][0]["insert"][0]
    assert first["name"] == (tmp_path / "first.mjs").as_uri()
    assert second["name"] == (tmp_path / "second.mjs").as_uri()
    assert first["config"]["persona"] == "./literal"
    assert first["id"] != second["id"]
