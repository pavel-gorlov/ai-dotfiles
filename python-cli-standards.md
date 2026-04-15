# Python CLI Tool: Stack & Development Standards

> Шаблон стандартов для Python CLI-проекта без БД и API.
> Основан на проверенных практиках из production проекта (planch).

---

## 1. Стек технологий

| Компонент | Инструмент | Версия | Назначение |
|-----------|-----------|--------|------------|
| Язык | Python | >=3.12 | Основной язык |
| Пакетный менеджер | Poetry | latest | Управление зависимостями, скрипты, публикация |
| CLI фреймворк | Typer / Click | latest | Парсинг аргументов, help, subcommands |
| Валидация конфигов | Pydantic | ^2.x | Модели конфигурации, environment variables |
| Форматирование | Black | ^24.x | Единый code style |
| Линтер | Ruff | ^0.5.x | Быстрый линтер (заменяет flake8, pyflakes, pycodestyle) |
| Сортировка импортов | isort | ^5.x | Автоматическая сортировка (профиль black) |
| Типизация | mypy | ^1.x | Статический анализ типов |
| Безопасность | Bandit | ^1.8.x | Поиск security-уязвимостей |
| Секреты | detect-secrets | ^1.5.x | Предотвращение утечки секретов в git |
| Тесты | pytest | ^8.x | Фреймворк тестирования |
| Покрытие | pytest-cov | ^4.x | Code coverage |
| Pre-commit | pre-commit | ^3.x | Git hooks для автоматических проверок |
| Коммиты | Commitizen | ^3.x | Conventional commits |

---

## 2. Структура проекта

```
my-cli-tool/
├── pyproject.toml          # Poetry config + tool configs
├── .pre-commit-config.yaml # Git hooks
├── .gitignore
├── README.md
├── CLAUDE.md               # Инструкции для AI-ассистентов
│
├── src/
│   └── my_cli_tool/
│       ├── __init__.py     # Версия пакета
│       ├── __main__.py     # python -m my_cli_tool
│       ├── cli.py          # Typer app, команды верхнего уровня
│       ├── commands/       # Подкоманды (по одному файлу на группу)
│       │   ├── __init__.py
│       │   ├── init.py     # my-cli init
│       │   └── run.py      # my-cli run
│       ├── core/           # Бизнес-логика (без зависимости от CLI)
│       │   ├── __init__.py
│       │   ├── config.py   # Pydantic Settings
│       │   └── errors.py   # Custom exceptions
│       ├── services/       # Сервисный слой
│       │   └── __init__.py
│       └── utils/          # Хелперы
│           └── __init__.py
│
└── tests/
    ├── conftest.py         # Shared fixtures
    ├── unit/               # Unit тесты (быстрые, без I/O)
    │   ├── test_config.py
    │   └── test_services.py
    ├── integration/        # Интеграционные (файловая система, процессы)
    │   └── test_commands.py
    └── e2e/                # End-to-end (CLI invocation через subprocess/CliRunner)
        └── test_cli.py
```

### Принципы структуры

- **`commands/`** — тонкие обёртки: парсят аргументы, вызывают `core/` или `services/`, форматируют вывод. Никакой бизнес-логики.
- **`core/`** — чистая логика, тестируется unit-тестами без CLI зависимостей.
- **`services/`** — операции с внешним миром (файлы, сеть, процессы).
- **`__main__.py`** — точка входа для `python -m my_cli_tool`.

---

## 3. Конфигурация инструментов

### `pyproject.toml`

```toml
[tool.poetry]
name = "my-cli-tool"
version = "0.1.0"
description = "Description"
authors = ["Author <email>"]
readme = "README.md"
packages = [{ include = "my_cli_tool", from = "src" }]

[tool.poetry.dependencies]
python = ">=3.12,<4.0"
typer = "^0.15.0"
pydantic = "^2.11.0"
pydantic-settings = "^2.10.0"
rich = "^13.0.0"  # Красивый вывод в терминале

[tool.poetry.group.dev.dependencies]
mypy = "^1.16.0"
pytest = "^8.4.0"
pytest-cov = "^4.1.0"
black = "^24.4.0"
ruff = "^0.5.0"
isort = "^5.13.0"
bandit = { extras = ["toml"], version = "^1.8.0" }
detect-secrets = "^1.5.0"
pre-commit = "^3.7.0"
commitizen = "^3.23.0"

[tool.poetry.scripts]
my-cli = "my_cli_tool.cli:app"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

# ──────────────────────────────────────────────
# Tool configs
# ──────────────────────────────────────────────

[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_ignores = true
plugins = ["pydantic.mypy"]
mypy_path = "src"

[tool.black]
line-length = 88

[tool.isort]
profile = "black"
line_length = 88

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
    "T20", # flake8-print (ловит забытые print() в production коде)
]

[tool.bandit]
exclude_dirs = ["tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: integration tests (file system, network)",
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
    "@(abc\\.)?abstractmethod",
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

  - repo: https://github.com/PyCQA/isort
    rev: 6.0.1
    hooks:
      - id: isort

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.16.1
    hooks:
      - id: mypy
        args: ['--config-file', 'pyproject.toml']
        additional_dependencies:
          - 'pydantic>=2.11'
          - 'pydantic-settings>=2.10'
          - 'typer>=0.15'

  - repo: https://github.com/PyCQA/bandit
    rev: 1.8.6
    hooks:
      - id: bandit
        args: ['-r', 'src', '-c', 'pyproject.toml']
        pass_filenames: false
        additional_dependencies: ['bandit[toml]']

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        stages: ['commit', 'push']

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

---

## 4. Code Style

### Именование

| Элемент | Стиль | Пример |
|---------|-------|--------|
| Функции, переменные | `snake_case` | `parse_config()`, `file_path` |
| Классы | `PascalCase` | `ConfigParser`, `CliError` |
| Константы | `UPPER_CASE` | `DEFAULT_TIMEOUT`, `MAX_RETRIES` |
| Приватные | `_prefix` | `_validate()`, `_cache` |
| Модули, пакеты | `snake_case` | `my_cli_tool`, `config.py` |
| CLI команды | `kebab-case` | `my-cli run-all`, `my-cli init` |

### Форматирование

- **Black** как единственный источник правды для форматирования
- Длина строки: **88 символов** (Black default)
- Абсолютные импорты вместо относительных: `from my_cli_tool.core.config import Settings`
- **isort** с профилем `black` для сортировки импортов

### Типизация

- **Обязательна** для всех публичных функций (параметры + возвращаемый тип)
- Для приватных — рекомендуется, но не обязательна
- `mypy --strict` в CI
- Используй `Optional[Type]` вместо `Type | None` (единообразие, mypy strict)
- Pydantic models для валидации входных данных и конфигурации

```python
# Хорошо
def process_file(path: Path, *, verbose: bool = False) -> ProcessResult:
    ...

# Плохо
def process_file(path, verbose=False):
    ...
```

### Документирование

- **Google-style docstrings** для публичных функций/классов
- Docstring обязателен, если функция не самоочевидна из имени + типов
- НЕ писать docstring для тривиальных функций где имя + типы достаточно
- Inline комментарии только для неочевидной логики

```python
def parse_config(path: Path) -> Config:
    """Parse and validate configuration file.

    Args:
        path: Path to YAML/TOML config file.

    Returns:
        Validated config object.

    Raises:
        ConfigError: If file is missing or invalid.
    """
```

---

## 5. Error Handling

### Иерархия исключений

```python
# src/my_cli_tool/core/errors.py

class CliToolError(Exception):
    """Base exception for all CLI tool errors."""
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code

class ConfigError(CliToolError):
    """Invalid or missing configuration."""

class InputError(CliToolError):
    """Invalid user input or file format."""

class ExternalError(CliToolError):
    """External service or process failure."""
```

### Правила

1. **Бизнес-логика** (`core/`, `services/`) бросает свои исключения (`CliToolError` и наследники)
2. **CLI слой** (`cli.py`, `commands/`) ловит их и конвертирует в user-friendly вывод с exit code
3. **Никогда** не глотать исключения молча (`except: pass`)
4. `SystemExit` и `KeyboardInterrupt` не ловить в бизнес-логике

```python
# commands/run.py — CLI слой
@app.command()
def run(config_path: Path) -> None:
    try:
        result = process(config_path)
        console.print(f"[green]Done:[/green] {result.summary}")
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}", err=True)
        raise typer.Exit(code=e.exit_code) from e
```

---

## 6. Testing

### Структура тестов

```
tests/
├── conftest.py         # Shared fixtures (tmp_path factories, mock configs)
├── unit/               # Быстрые, без I/O, без subprocess
│   ├── test_config.py
│   └── test_parser.py
├── integration/        # Файловая система, внешние процессы
│   └── test_file_processing.py
└── e2e/                # Полный CLI через CliRunner или subprocess
    └── test_cli.py
```

### Правила

| Правило | Обоснование |
|---------|-------------|
| Тесты обязательны перед merge | Нет тестов = нет merge |
| Coverage >= 80% | `fail_under = 80` в pyproject.toml |
| Unit тесты не трогают файловую систему | Используй `tmp_path` fixture для integration |
| Каждый тест изолирован | Не зависит от порядка запуска или результатов других тестов |
| Fixture вместо setup/teardown | pytest fixtures с `yield` для cleanup |
| Один assert на тест (рекомендация) | Исключение: тесты пайплайнов где проверяется несколько аспектов результата |
| Никаких `sleep()` в тестах | Используй моки для I/O операций |

### Пример unit-теста

```python
# tests/unit/test_config.py
import pytest
from my_cli_tool.core.config import Settings
from my_cli_tool.core.errors import ConfigError

def test_settings_from_valid_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("timeout: 30\nverbose: true")

    settings = Settings.from_file(config_file)

    assert settings.timeout == 30
    assert settings.verbose is True

def test_settings_from_missing_file() -> None:
    with pytest.raises(ConfigError, match="not found"):
        Settings.from_file(Path("/nonexistent/config.yaml"))
```

### Пример E2E теста (CLI)

```python
# tests/e2e/test_cli.py
from typer.testing import CliRunner
from my_cli_tool.cli import app

runner = CliRunner()

def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

def test_run_with_valid_config(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("timeout: 10")

    result = runner.invoke(app, ["run", str(config)])

    assert result.exit_code == 0
    assert "Done" in result.stdout

def test_run_with_invalid_config() -> None:
    result = runner.invoke(app, ["run", "/nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.stdout
```

### Команды запуска

```bash
# Все тесты
poetry run pytest

# Только unit
poetry run pytest tests/unit/

# С покрытием
poetry run pytest --cov --cov-report=term-missing

# Конкретный тест
poetry run pytest tests/unit/test_config.py -k "test_valid"

# Пропуск медленных
poetry run pytest -m "not slow"
```

---

## 7. Git Workflow

### Ветки

- `main` — production-ready код
- `feat/<name>` — новая функциональность
- `fix/<name>` — исправление бага
- `refactor/<name>` — рефакторинг без изменения поведения

### Conventional Commits (Commitizen)

```
feat: add config file validation
fix: handle empty input gracefully
refactor: extract parsing logic into separate module
test: add unit tests for config parser
docs: update CLI usage examples
chore: update dependencies
```

### Pre-commit workflow

```bash
# Установка хуков (один раз)
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg

# Ручной запуск всех проверок
poetry run pre-commit run --all-files

# Что происходит при git commit:
# 1. Black форматирует код
# 2. Ruff проверяет и автофиксит
# 3. isort сортирует импорты
# 4. mypy проверяет типы
# 5. Bandit ищет security-проблемы
# 6. detect-secrets проверяет на утечки
# 7. commitizen валидирует commit message
```

**ВАЖНО:** Black, Ruff и isort могут **автоматически менять файлы**. После первого неудачного `git commit`:
1. Проверь `git diff` — хуки могли изменить файлы
2. Добавь изменения: `git add .`
3. Повтори commit

---

## 8. CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
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
      - uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
```

---

## 9. Быстрый старт нового проекта

```bash
# Создание проекта
mkdir my-cli-tool && cd my-cli-tool
poetry init
poetry add python@">=3.12,<4.0"
poetry add typer pydantic pydantic-settings rich
poetry add --group dev mypy pytest pytest-cov black ruff isort bandit detect-secrets pre-commit commitizen

# Структура
mkdir -p src/my_cli_tool/{commands,core,services,utils}
mkdir -p tests/{unit,integration,e2e}
touch src/my_cli_tool/__init__.py src/my_cli_tool/__main__.py src/my_cli_tool/cli.py
touch tests/conftest.py

# Git hooks
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg

# Первый запуск проверок
poetry run pre-commit run --all-files
poetry run pytest
```

---

## 10. Checklist для Code Review

- [ ] Типизация: все публичные функции имеют аннотации типов
- [ ] Тесты: новая логика покрыта unit-тестами, новые команды — e2e тестами
- [ ] Coverage: не упал ниже 80%
- [ ] Lint: `pre-commit run --all-files` проходит без ошибок
- [ ] Security: Bandit не нашёл проблем
- [ ] Secrets: нет захардкоженных токенов, паролей, ключей
- [ ] Errors: исключения наследуются от `CliToolError`, CLI ловит и показывает user-friendly
- [ ] Docs: docstring для неочевидных публичных функций
- [ ] Commits: conventional commits format
- [ ] No print(): использовать `rich.console` или `typer.echo` вместо `print()`
