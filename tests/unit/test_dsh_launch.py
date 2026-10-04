"""Pure launcher argument, runtime-resolution and subprocess boundary tests."""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from ai_dotfiles.core.dsh_config import collect_dsh_configuration
from ai_dotfiles.core.dsh_launch import (
    DshLaunchArguments,
    DshLaunchPlan,
    discover_dsh_runtime,
    execute_dsh_launch,
    parse_dsh_launch_arguments,
)
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.dsh_native import DshNativeRuntime
from ai_dotfiles.core.errors import ConfigError, ExternalError


@pytest.mark.parametrize(
    ("argv", "profile", "app"),
    [
        (
            ["web", "--port", "9012", "--patch", "literal"],
            "web",
            ("--port", "9012", "--patch", "literal"),
        ),
        (
            ["--profile", "headless", "task; $(touch no)", "--json"],
            "headless",
            ("task; $(touch no)", "--json"),
        ),
        (["--profile=web", "--help"], "web", ("--help",)),
        (
            ["custom", "--", "--profile", "literal"],
            "custom",
            ("--", "--profile", "literal"),
        ),
    ],
)
def test_native_leading_flags_leave_app_argv_verbatim(
    argv: list[str], profile: str, app: tuple[str, ...]
) -> None:
    result = parse_dsh_launch_arguments(argv, cwd=Path("/project"))
    assert result.profile == profile
    assert result.app_args == app


def test_repeatable_overlay_order_and_literal_paths() -> None:
    result = parse_dsh_launch_arguments(
        ["web", "--patch", "a b.json", "--patch=../last.json", "task"],
        cwd=Path("/project"),
    )
    assert result.patch_files == (Path("/project/a b.json"), Path("/last.json"))
    assert result.app_args == ("task",)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--profile"],
        ["--patch"],
        ["--profile="],
        ["web", "--profile", "other"],
        ["desktop"],
        ["../web"],
        ["plugin"],
        ["web", "--from-default-profile", "web"],
        ["web", "--dump-config"],
        ["web", "--dump-default-config"],
        ["web", "--dump-config-schema"],
    ],
)
def test_invalid_or_mutating_invocations_fail_before_launch(args: list[str]) -> None:
    with pytest.raises(ConfigError):
        parse_dsh_launch_arguments(args, cwd=Path("/project"))


def test_missing_runtime_is_actionable_and_never_installs() -> None:
    with patch(
        "ai_dotfiles.core.dsh_launch.shutil.which", return_value=None
    ), pytest.raises(ExternalError, match="install.*separately"):
        discover_dsh_runtime(process_env={"PATH": "/explicit"})


def test_wrapper_is_refused_without_executing_it() -> None:
    with patch(
        "ai_dotfiles.core.dsh_launch.shutil.which", return_value="/wrapper/dsh"
    ), patch.object(Path, "resolve", return_value=Path("/wrapper/dsh")), pytest.raises(
        ConfigError, match="wrapper"
    ):
        discover_dsh_runtime(process_env={"PATH": "/explicit"})


def test_official_bin_uses_explicit_path_for_node() -> None:
    runtime = DshNativeRuntime(
        Path("/official/dsh"), Path("/node"), Path("/official/dsh/lib/bin.js")
    )
    with patch(
        "ai_dotfiles.core.dsh_launch.shutil.which",
        side_effect=[str(runtime.cli), "/node"],
    ) as which, patch.object(Path, "resolve", side_effect=lambda: runtime.cli), patch(
        "ai_dotfiles.core.dsh_launch.resolve_dsh_runtime", return_value=runtime
    ) as resolve:
        assert discover_dsh_runtime(process_env={"PATH": "/explicit"}) == runtime
    assert which.call_args_list[1].kwargs == {"path": "/explicit"}
    resolve.assert_called_once_with(runtime.package_dir, node="/node")


@pytest.mark.parametrize(("status", "expected"), [(0, 0), (17, 17), (-15, 143)])
def test_shell_free_process_environment_and_status(status: int, expected: int) -> None:
    layout = project_layout(Path("/project"))
    config = collect_dsh_configuration([], layout)
    runtime = DshNativeRuntime(
        Path("/official/dsh"), Path("/node"), Path("/official/dsh/lib/bin.js")
    )
    plan = DshLaunchPlan(
        runtime,
        Path("/project/sub"),
        DshLaunchArguments("web", (), ("a b", "$(touch no)", "--port", "0")),
        config,
        (),
        {
            "rootPath": "/owned/root",
            "inspected": {},
            "sentinelHeader": "MCP_PRIVATE_SENTINEL_456",
        },
        (),
    )
    with patch(
        "ai_dotfiles.core.dsh_launch.subprocess.run",
        return_value=CompletedProcess([], status),
    ) as run, patch(
        "ai_dotfiles.core.dsh_launch.tempfile.NamedTemporaryFile"
    ) as temporary:
        temporary.return_value.__enter__.return_value.name = "/private/tmp/request.json"
        assert (
            execute_dsh_launch(plan, process_env={"A": "", "DSH_HOME": "/explicit"})
            == expected
        )
    argv = run.call_args.args[0]
    assert argv[-4:] == ["a b", "$(touch no)", "--port", "0"]
    assert argv[:3] == ["/node", "--input-type=module", "-e"]
    assert argv[4] == "--"
    assert "MCP_PRIVATE_SENTINEL_456" not in " ".join(argv)
    assert "readFileSync" in argv[3]
    temporary.return_value.__enter__.return_value.flush.assert_called_once()
    assert run.call_args.kwargs == {
        "shell": False,
        "cwd": Path("/project/sub"),
        "env": {"A": "", "DSH_HOME": "/explicit"},
        "check": False,
    }


def test_spawn_error_is_actionable() -> None:
    layout = project_layout(Path("/project"))
    config = collect_dsh_configuration([], layout)
    runtime = DshNativeRuntime(
        Path("/official/dsh"), Path("/node"), Path("/official/dsh/lib/bin.js")
    )
    plan = DshLaunchPlan(
        runtime,
        Path("/project"),
        DshLaunchArguments("web", (), ()),
        config,
        (),
        {"rootPath": "/owned/root", "inspected": {}},
        (),
    )
    with patch(
        "ai_dotfiles.core.dsh_launch.subprocess.run", side_effect=OSError("missing")
    ), patch(
        "ai_dotfiles.core.dsh_launch.tempfile.NamedTemporaryFile"
    ) as temporary, pytest.raises(
        ExternalError, match="could not start"
    ):
        temporary.return_value.__enter__.return_value.name = "/private/tmp/request.json"
        execute_dsh_launch(plan, process_env={})
