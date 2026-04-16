# Step 0: Dev infrastructure

## Goal

Set up development tooling so that quality gates work from the very first commit. After this step: `poetry install` works, `poetry run pre-commit run --all-files` passes on empty project, CI pipeline exists.

## Files to create

### `pyproject.toml`

```toml
[tool.poetry]
name = "ai-dotfiles"
version = "0.1.0"
description = "Package manager for Claude Code configuration"
authors = ["Pavel Gorlov"]
readme = "README.md"
license = "MIT"
packages = [{ include = "ai_dotfiles", from = "src" }]

[tool.poetry.dependencies]
python = ">=3.12,<4.0"
click = "^8.1"

[tool.poetry.group.dev.dependencies]
mypy = "^1.16"
pytest = "^8.4"
pytest-cov = "^4.1"
black = "^24.4"
ruff = "^0.5"
pre-commit = "^3.7"
commitizen = "^3.23"

[tool.poetry.scripts]
ai-dotfiles = "ai_dotfiles.cli:cli"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

# ── Tool configs ──

[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_ignores = true
mypy_path = "src"

[tool.black]
line-length = 88

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "UP",  # pyupgrade
    "B",   # bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: marks tests as slow",
    "integration: integration tests (filesystem, symlinks)",
]

[tool.coverage.run]
source = ["src"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]

[tool.commitizen]
name = "cz_conventional_commits"
version = "0.1.0"
tag_format = "v$version"
```

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 25.1.0
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.12.2
    hooks:
      - id: ruff
        args: ['--fix']

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.16.1
    hooks:
      - id: mypy
        args: ['--config-file', 'pyproject.toml']
        additional_dependencies: ['click>=8.1']

  - repo: https://github.com/commitizen-tools/commitizen
    rev: v4.8.3
    hooks:
      - id: commitizen
        stages: ['commit-msg']
        pass_filenames: false

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
```

### `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install poetry && poetry install
      - run: poetry run pre-commit run --all-files

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install poetry && poetry install
      - run: poetry run pytest --cov --cov-report=xml
```

### `.gitignore` (update)

Append to existing:
```
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
dist/
*.egg-info/
.venv/
htmlcov/
coverage.xml
```

### Minimal source stubs (needed for tools to pass)

Tools (mypy, ruff, black) need at least one Python file to not fail on empty `src/`:

```
src/ai_dotfiles/__init__.py     # __version__ = "0.1.0"
```

And test dir:

```
tests/__init__.py               # empty
```

## Verification

```bash
# 1. Install
poetry install

# 2. Tools work on stubs
poetry run mypy src/                     # Success, no errors
poetry run ruff check src/ tests/        # no errors
poetry run black --check src/ tests/     # formatted

# 3. Test runner works
poetry run pytest                        # 0 tests collected, no errors

# 4. Pre-commit
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg
poetry run pre-commit run --all-files    # all pass
```

## Definition of Done

- [ ] `pyproject.toml` exists with all tool configs
- [ ] `.pre-commit-config.yaml` exists
- [ ] `.github/workflows/ci.yml` exists
- [ ] `.gitignore` updated with Python/tooling entries
- [ ] `poetry install` completes without errors
- [ ] `poetry run mypy src/` — passes (no errors)
- [ ] `poetry run ruff check src/ tests/` — passes (no errors)
- [ ] `poetry run black --check src/ tests/` — passes (all formatted)
- [ ] `poetry run pytest` — runs (0 collected, no errors)
- [ ] `poetry run pre-commit run --all-files` — all hooks pass
- [ ] Pre-commit hooks installed (`commit-msg` hook included)

## Commit message

`chore: dev infrastructure — Poetry, Black, Ruff, mypy, pre-commit, CI`
