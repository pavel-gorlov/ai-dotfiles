"""Unit tests for ai_dotfiles.vendors.deps."""

from __future__ import annotations

import subprocess
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
    install_cmd: dict[str, list[str]] | None = None,
    manual_hint: str = "install it manually",
) -> Dependency:
    return Dependency(
        name=name,
        check=lambda: installed,
        install_cmd=install_cmd or {},
        manual_hint=manual_hint,
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


def test_ensure_raises_with_install_hint() -> None:
    vendor = _vendor(
        _dep(name="npx", installed=False, manual_hint="brew install node"),
    )

    with pytest.raises(ExternalError) as exc_info:
        deps.ensure(vendor)

    msg = str(exc_info.value)
    assert "npx" in msg
    assert "brew install node" in msg
    assert "ai-dotfiles vendor fake deps install" in msg


def test_ensure_silent_when_all_present() -> None:
    vendor = _vendor(_dep(name="git", installed=True))
    # Does not raise.
    deps.ensure(vendor)


# ── install ────────────────────────────────────────────────────────────────


def test_install_runs_subprocess_for_missing_dep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={
                "darwin": ["brew", "install", "node"],
                "linux": ["apt", "install", "-y", "nodejs"],
                "win32": ["choco", "install", "nodejs"],
            },
        )
    )

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deps, "_platform_key", lambda: "linux")
    monkeypatch.setattr(deps.subprocess, "run", fake_run)

    deps.install(vendor, yes=True)

    assert calls == [["apt", "install", "-y", "nodejs"]]


def test_install_prompts_and_aborts_on_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={"linux": ["apt", "install", "-y", "nodejs"]},
        )
    )

    called: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:  # pragma: no cover
        called.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deps, "_platform_key", lambda: "linux")
    monkeypatch.setattr(deps.click, "confirm", lambda *a, **kw: False)
    monkeypatch.setattr(deps.subprocess, "run", fake_run)

    deps.install(vendor, yes=False)

    assert called == []


def test_install_noop_when_nothing_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(_dep(name="git", installed=True))

    def boom(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("should not run")

    monkeypatch.setattr(deps.subprocess, "run", boom)

    deps.install(vendor, yes=True)


def test_install_raises_when_platform_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={"darwin": ["brew", "install", "node"]},
            manual_hint="See https://nodejs.org/ for install instructions.",
        )
    )

    monkeypatch.setattr(deps, "_platform_key", lambda: "linux")

    with pytest.raises(ExternalError) as exc_info:
        deps.install(vendor, yes=True)

    msg = str(exc_info.value)
    assert "No automatic install" in msg
    assert "linux" in msg
    assert "https://nodejs.org/" in msg


def test_install_raises_when_brew_missing_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={"darwin": ["brew", "install", "node"]},
        )
    )

    monkeypatch.setattr(deps, "_platform_key", lambda: "darwin")
    monkeypatch.setattr(deps.shutil, "which", lambda name: None)

    with pytest.raises(ExternalError, match="Homebrew"):
        deps.install(vendor, yes=True)


def test_install_surfaces_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={"linux": ["apt", "install", "-y", "nodejs"]},
        )
    )

    def boom(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd)

    monkeypatch.setattr(deps, "_platform_key", lambda: "linux")
    monkeypatch.setattr(deps.subprocess, "run", boom)

    with pytest.raises(ExternalError, match="Failed to install 'npx'"):
        deps.install(vendor, yes=True)


def test_install_surfaces_missing_installer_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = _vendor(
        _dep(
            name="npx",
            installed=False,
            install_cmd={"linux": ["apt", "install", "-y", "nodejs"]},
            manual_hint="install apt first",
        )
    )

    def boom(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError()

    monkeypatch.setattr(deps, "_platform_key", lambda: "linux")
    monkeypatch.setattr(deps.subprocess, "run", boom)

    with pytest.raises(ExternalError, match="Installer executable not found"):
        deps.install(vendor, yes=True)


def test_platform_key_recognizes_common_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps.sys, "platform", "linux")
    assert deps._platform_key() == "linux"
    monkeypatch.setattr(deps.sys, "platform", "linux2")
    assert deps._platform_key() == "linux"
    monkeypatch.setattr(deps.sys, "platform", "darwin")
    assert deps._platform_key() == "darwin"
    monkeypatch.setattr(deps.sys, "platform", "win32")
    assert deps._platform_key() == "win32"
