"""Integration tests for ``core/runtime.py``.

The subprocess calls (``uv venv`` / ``uv pip install``) are mocked so
tests stay fast and deterministic. The fakes mimic just enough of the
filesystem effect (creating ``<venv>/bin/python``) to satisfy the
production code path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_dotfiles.core import runtime


def _write_domain(
    catalog: Path,
    name: str,
    *,
    requires: dict[str, list[str]] | None = None,
    bin_files: dict[str, str] | None = None,
) -> Path:
    domain = catalog / name
    domain.mkdir(parents=True)
    meta: dict[str, Any] = {"name": name}
    if requires is not None:
        meta["requires"] = requires
    (domain / "domain.json").write_text(json.dumps(meta), encoding="utf-8")
    if bin_files:
        bin_dir = domain / "bin"
        bin_dir.mkdir()
        for fname, body in bin_files.items():
            entry = bin_dir / fname
            entry.write_text(body, encoding="utf-8")
            entry.chmod(0o755)
    return domain


def _install_subprocess_fake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    has_uv: bool = True,
) -> list[list[str]]:
    """Patch out subprocess + uv detection. Returns the command log."""
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        calls.append(cmd)
        # Synthesize a usable venv layout: provisioning code probes
        # `<venv>/bin/python` to decide whether the venv exists already.
        if cmd[:2] == ["uv", "venv"] or (len(cmd) >= 3 and cmd[1:3] == ["-m", "venv"]):
            venv = Path(cmd[-1])
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\nexec true\n")
            (venv / "bin" / "python").chmod(0o755)

        class _Result:
            stdout = ""
            stderr = ""
            returncode = 0

        return _Result()

    monkeypatch.setattr(runtime.subprocess, "run", _fake_run)
    monkeypatch.setattr(runtime, "_has_uv", lambda: has_uv)
    return calls


@pytest.mark.integration
def test_provision_creates_shim_and_venv(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "taskmanager",
        requires={"python": ["click>=8"]},
        bin_files={"tm": "#!/usr/bin/env python3\nprint('tm')\n"},
    )
    calls = _install_subprocess_fake(monkeypatch)

    result = runtime.provision_domain_runtime(catalog, "taskmanager")

    assert result.shims_created == ["tm"]
    assert result.shims_updated == []
    assert result.python_packages == ["click>=8"]
    assert result.venv_path == tmp_storage / "venvs" / "taskmanager"

    shim = tmp_storage / "bin" / "tm"
    assert shim.is_file()
    body = shim.read_text(encoding="utf-8")
    assert runtime._SHIM_HEADER in body
    assert "domain: taskmanager" in body
    assert str(tmp_storage / "venvs" / "taskmanager" / "bin" / "python") in body
    # Shim must be executable.
    assert shim.stat().st_mode & 0o111

    # Two subprocess calls: uv venv + uv pip install.
    assert calls[0][:2] == ["uv", "venv"]
    assert calls[1][:3] == ["uv", "pip", "install"]


@pytest.mark.integration
def test_provision_idempotent(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "taskmanager",
        requires={"python": ["click>=8"]},
        bin_files={"tm": "#!/usr/bin/env python3\n"},
    )
    _install_subprocess_fake(monkeypatch)

    first = runtime.provision_domain_runtime(catalog, "taskmanager")
    assert first.shims_created == ["tm"]

    second = runtime.provision_domain_runtime(catalog, "taskmanager")
    # Same shim body — no create, no update.
    assert second.shims_created == []
    assert second.shims_updated == []


@pytest.mark.integration
def test_provision_no_python_uses_direct_shim(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "tools",
        bin_files={"hello.sh": "#!/bin/sh\necho hi\n"},
    )
    calls = _install_subprocess_fake(monkeypatch)

    result = runtime.provision_domain_runtime(catalog, "tools")

    assert result.shims_created == ["hello.sh"]
    assert result.venv_path is None
    assert calls == []  # No venv subprocess invocations.

    shim_body = (tmp_storage / "bin" / "hello.sh").read_text(encoding="utf-8")
    target = (catalog / "tools" / "bin" / "hello.sh").resolve()
    assert f'exec "{target}"' in shim_body


@pytest.mark.integration
def test_provision_skips_user_owned_file(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "taskmanager",
        bin_files={"tm": "#!/bin/sh\n"},
    )
    _install_subprocess_fake(monkeypatch)

    bin_dir = tmp_storage / "bin"
    bin_dir.mkdir()
    user_file = bin_dir / "tm"
    user_file.write_text("#!/bin/sh\necho user\n", encoding="utf-8")

    result = runtime.provision_domain_runtime(catalog, "taskmanager")

    assert result.shims_created == []
    assert result.shims_skipped == [("tm", "user-owned file at target")]
    # User's file untouched.
    assert user_file.read_text(encoding="utf-8") == "#!/bin/sh\necho user\n"


@pytest.mark.integration
def test_provision_warns_on_missing_cli(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "taskmanager",
        requires={"cli": ["definitely-not-a-real-binary-xyz"]},
        bin_files={"tm": "#!/bin/sh\n"},
    )
    _install_subprocess_fake(monkeypatch)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)

    result = runtime.provision_domain_runtime(catalog, "taskmanager")

    assert result.missing_cli == ["definitely-not-a-real-binary-xyz"]


@pytest.mark.integration
def test_tear_down_removes_shim_and_venv(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(
        catalog,
        "taskmanager",
        requires={"python": ["click>=8"]},
        bin_files={"tm": "#!/bin/sh\n"},
    )
    _install_subprocess_fake(monkeypatch)
    runtime.provision_domain_runtime(catalog, "taskmanager")

    shim = tmp_storage / "bin" / "tm"
    venv = tmp_storage / "venvs" / "taskmanager"
    assert shim.is_file()
    assert venv.is_dir()

    removed = runtime.tear_down_domain_runtime(catalog, "taskmanager")

    assert removed == ["tm"]
    assert not shim.exists()
    assert not venv.exists()


@pytest.mark.integration
def test_tear_down_leaves_other_domain_shims(
    tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_storage / "catalog"
    _write_domain(catalog, "domA", bin_files={"a": "#!/bin/sh\n"})
    _write_domain(catalog, "domB", bin_files={"b": "#!/bin/sh\n"})
    _install_subprocess_fake(monkeypatch)
    runtime.provision_domain_runtime(catalog, "domA")
    runtime.provision_domain_runtime(catalog, "domB")

    removed = runtime.tear_down_domain_runtime(catalog, "domA")

    assert removed == ["a"]
    assert not (tmp_storage / "bin" / "a").exists()
    assert (tmp_storage / "bin" / "b").is_file()


@pytest.mark.integration
def test_bin_dir_on_path(monkeypatch: pytest.MonkeyPatch, tmp_storage: Path) -> None:
    bin_dir = tmp_storage / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"/usr/bin:{bin_dir}")
    assert runtime.bin_dir_on_path() is True

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert runtime.bin_dir_on_path() is False
