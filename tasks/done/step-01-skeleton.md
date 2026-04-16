# Step 1: Project skeleton

## Goal

Create the code skeleton: CLI entry point, UI helpers, error hierarchy, and test fixtures. After this step: `ai-dotfiles --version` works, `python -m ai_dotfiles` works, all quality gates pass.

**Depends on**: Step 0 (infrastructure must be in place).

## Files to create

### `src/ai_dotfiles/__main__.py`

```python
from ai_dotfiles.cli import cli

cli()
```

### `src/ai_dotfiles/cli.py`

- `@click.group()` with `@click.version_option()`
- Empty body (`pass`)

### `src/ai_dotfiles/ui.py`

Wrappers around `click.secho` (no `print()` anywhere):

```python
def info(msg: str) -> None      # default color
def success(msg: str) -> None   # green, prefix "+"
def warn(msg: str) -> None      # yellow, prefix "!"
def error(msg: str) -> None     # red, prefix "x", to stderr
def confirm(msg: str) -> bool   # click.confirm wrapper
```

### `src/ai_dotfiles/core/__init__.py`

Empty.

### `src/ai_dotfiles/core/errors.py`

```python
class AiDotfilesError(Exception):
    """Base exception for all ai-dotfiles errors."""
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code

class ConfigError(AiDotfilesError):
    """Invalid or missing configuration / manifest."""

class ElementError(AiDotfilesError):
    """Invalid element specifier or missing element in catalog."""

class LinkError(AiDotfilesError):
    """Symlink operation failed."""

class ExternalError(AiDotfilesError):
    """External process failure (git clone, etc.)."""
```

Commands catch `AiDotfilesError` subclasses and convert to user-friendly output with exit code.

### `src/ai_dotfiles/commands/__init__.py`

Empty.

### `src/ai_dotfiles/scaffold/__init__.py`

Empty.

### `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/e2e/__init__.py`

Empty.

### `tests/conftest.py`

```python
import pytest
from pathlib import Path

@pytest.fixture
def tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set AI_DOTFILES_HOME to a temp dir, return the path."""
    storage = tmp_path / ".ai-dotfiles"
    storage.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))
    return storage

@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temp project dir with .git, return the path."""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".git").mkdir()
    return project

@pytest.fixture
def tmp_claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override HOME so ~/.claude/ points to temp."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path
```

## Verification

```bash
ai-dotfiles --version                    # 0.1.0
python -m ai_dotfiles --version          # 0.1.0
poetry run pytest tests/ -v              # 0 tests collected, no errors
poetry run mypy src/                     # no errors
poetry run ruff check src/ tests/        # no errors
poetry run black --check src/ tests/     # formatted
```

## Definition of Done

- [ ] `ai-dotfiles --version` prints `0.1.0`
- [ ] `python -m ai_dotfiles --version` works
- [ ] `from ai_dotfiles.ui import info, success, warn, error` works
- [ ] `from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, ElementError, LinkError, ExternalError` works
- [ ] `tests/conftest.py` fixtures importable: `tmp_storage`, `tmp_project`, `tmp_claude_home`
- [ ] `poetry run pytest tests/ -v` — no import errors
- [ ] `poetry run mypy src/` — passes strict mode
- [ ] `poetry run ruff check src/ tests/` — no errors
- [ ] `poetry run black --check src/ tests/` — all formatted

## Commit message

`feat: project skeleton — CLI entry point, UI helpers, error hierarchy, test fixtures`
