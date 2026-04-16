"""Unit tests for ai_dotfiles.vendors.deps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ai_dotfiles.core.errors import ExternalError
from ai_dotfiles.vendors import deps
from ai_dotfiles.vendors.base import Dependency


@dataclass
class _FakeVendor:
    name: str
    display_name: str
    description: str
    deps: tuple[Dependency, ...]

    def list_source(self, source: str) -> list[str]:  # pragma: no cover - protocol
        return []

    def fetch(
        self, source: str, *, select: tuple[str, ...] | None, workdir: Any
    ) -> list[Any]:  # pragma: no cover - protocol
        return []


def _dep(
    *,
    name: str = "fake",
    installed: bool = True,
    install_url: str = "https://example.com/",
) -> Dependency:
    return Dependency(
        name=name,
        check=lambda: installed,
        install_url=install_url,
    )


def _vendor(*dependencies: Dependency) -> _FakeVendor:
    return _FakeVendor(
        name="fake",
        display_name="Fake",
        description="test vendor",
        deps=tuple(dependencies),
    )


# ── check ──────────────────────────────────────────────────────────────────


def test_check_returns_missing_deps() -> None:
    present = _dep(name="git", installed=True)
    absent = _dep(name="npx", installed=False)

    missing = deps.check(_vendor(present, absent))

    assert missing == [absent]


def test_check_returns_empty_when_all_present() -> None:
    vendor = _vendor(_dep(name="git"), _dep(name="npx"))
    assert deps.check(vendor) == []


# ── ensure ─────────────────────────────────────────────────────────────────


def test_ensure_raises_with_install_url() -> None:
    vendor = _vendor(
        _dep(name="npx", installed=False, install_url="https://nodejs.org/"),
    )

    with pytest.raises(ExternalError) as exc_info:
        deps.ensure(vendor)

    msg = str(exc_info.value)
    assert "missing dependency 'npx'; install: https://nodejs.org/" in msg


def test_ensure_lists_every_missing_dep() -> None:
    vendor = _vendor(
        _dep(name="git", installed=False, install_url="https://git-scm.com/"),
        _dep(name="npx", installed=False, install_url="https://nodejs.org/"),
    )

    with pytest.raises(ExternalError) as exc_info:
        deps.ensure(vendor)

    msg = str(exc_info.value)
    assert "missing dependency 'git'; install: https://git-scm.com/" in msg
    assert "missing dependency 'npx'; install: https://nodejs.org/" in msg


def test_ensure_silent_when_all_present() -> None:
    vendor = _vendor(_dep(name="git", installed=True))
    # Does not raise.
    deps.ensure(vendor)
