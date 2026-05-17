"""Unit tests for ai_dotfiles.core.targets."""

from __future__ import annotations

import pytest

from ai_dotfiles.core.elements import ElementType
from ai_dotfiles.core.targets import (
    RENDER_POLICY,
    RenderMode,
    Target,
    render_policy_for,
)


def test_target_values() -> None:
    assert Target.CLAUDE.value == "claude"
    assert Target.CODEX.value == "codex"


def test_render_policy_covers_every_target_and_element_type() -> None:
    for target in Target:
        assert target in RENDER_POLICY
        for element_type in ElementType:
            assert element_type in RENDER_POLICY[target]


def test_claude_policy_is_all_symlink() -> None:
    for element_type in ElementType:
        assert render_policy_for(Target.CLAUDE, element_type).mode is RenderMode.SYMLINK


@pytest.mark.parametrize(
    ("element_type", "expected_mode", "expected_subdir"),
    [
        (ElementType.SKILL, RenderMode.RENDER, "skills"),
        (ElementType.AGENT, RenderMode.RENDER, "agents"),
        (ElementType.RULE, RenderMode.SKIP, None),
        (ElementType.DOMAIN, RenderMode.SYMLINK, None),
    ],
)
def test_codex_policy(
    element_type: ElementType,
    expected_mode: RenderMode,
    expected_subdir: str | None,
) -> None:
    policy = render_policy_for(Target.CODEX, element_type)
    assert policy.mode is expected_mode
    assert policy.subdir == expected_subdir


def test_skip_policy_has_no_subdir() -> None:
    # A SKIP element type has no destination — subdir must be None.
    for target in Target:
        for element_type in ElementType:
            policy = render_policy_for(target, element_type)
            if policy.mode is RenderMode.SKIP:
                assert policy.subdir is None


def test_policy_objects_are_frozen() -> None:
    policy = render_policy_for(Target.CODEX, ElementType.SKILL)
    with pytest.raises(AttributeError):
        policy.mode = RenderMode.SYMLINK  # type: ignore[misc]
