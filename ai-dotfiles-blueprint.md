# ai-dotfiles

CLI-тул для управления конфигурацией Claude Code. Работает как пакетный менеджер: manifest-файл в проекте, `install` на другой машине восстанавливает всё.

Open source (CLI) + приватное хранилище (конфигурация).

## Модель: как npm

| npm                          | ai-dotfiles                         |
|------------------------------|--------------------------------------|
| `npm init`                   | `ai-dotfiles init`                   |
| `npm install`                | `ai-dotfiles install`                |
| `npm install express`        | `ai-dotfiles add @python`            |
| `npm install -g typescript`  | `ai-dotfiles add -g skill:web-research` |
| `npm uninstall express`      | `ai-dotfiles remove @python`         |
| `npm list`                   | `ai-dotfiles list`                   |
| `package.json`               | `ai-dotfiles.json`                   |
| `node_modules/`              | симлинки в `.claude/`                 |
| кэш пакетов                 | `~/.ai-dotfiles/`                    |

## Хранилище: ~/.ai-dotfiles/

Создаётся при `ai-dotfiles init -g`. Это git-репо с конфигурацией.

```
~/.ai-dotfiles/
├── global/                         # Физические файлы → ~/.claude/
│   ├── CLAUDE.md                   # Глобальные инструкции
│   ├── settings.json               # Permissions, env, hooks
│   ├── hooks/                      # Глобальные хук-скрипты
│   │   ├── post-edit-lint.sh
│   │   └── pre-commit-check.sh
│   └── output-styles/
│       └── concise-ru.md
│
├── global.json                 # Манифест: что из catalog/ ставить глобально
│
├── catalog/                        # Всё подключаемое
│   ├── _example/                   # Образцовый домен
│   │   ├── skills/example-skill/SKILL.md
│   │   ├── agents/example-agent.md
│   │   ├── rules/example-style.md
│   │   ├── hooks/example-lint.sh
│   │   └── settings.fragment.json
│   ├── skills/                     # Standalone скиллы
│   ├── agents/                     # Standalone агенты
│   └── rules/                      # Standalone правила
│
├── stacks/                         # Пресеты
│   └── _example.conf
│
└── README.md
```

## Манифест: ai-dotfiles.json

Файл в **корне проекта** (не в .claude/). Коммитится в git. На другой машине — `ai-dotfiles install`.

```json
{
  "packages": [
    "@python",
    "@telegram-api",
    "skill:code-review",
    "skill:git-workflow",
    "agent:researcher",
    "rule:security"
  ]
}
```

Глобальный аналог — `~/.ai-dotfiles/global.json`:

```json
{
  "packages": [
    "skill:web-research",
    "agent:summarizer"
  ]
}
```

## Команды

```
# --- Проект / Глобальное окружение ---

ai-dotfiles init                  Создать ai-dotfiles.json в корне проекта
ai-dotfiles init -g               Создать хранилище ~/.ai-dotfiles/ со scaffold
ai-dotfiles init -g --from <url>  Клонировать существующее хранилище

ai-dotfiles install               Прочитать ai-dotfiles.json → создать симлинки
ai-dotfiles install -g            Линковать global/ → ~/.claude/ + global.json

ai-dotfiles add <items...>        Добавить в ai-dotfiles.json + создать симлинки
ai-dotfiles add -g <items...>     Добавить в global.json + линковать в ~/.claude/

ai-dotfiles remove <items...>     Убрать из ai-dotfiles.json + удалить симлинки
ai-dotfiles remove -g <items...>  Убрать из global.json + удалить из ~/.claude/

ai-dotfiles list                  Содержимое ai-dotfiles.json
ai-dotfiles list -g               Содержимое global.json
ai-dotfiles list --available      Всё в catalog/ и stacks/

ai-dotfiles status                Валидация симлинков, merged hooks

# --- Standalone элементы ---

ai-dotfiles create skill <n>      Создать catalog/skills/<n>/SKILL.md
ai-dotfiles create agent <n>      Создать catalog/agents/<n>.md
ai-dotfiles create rule <n>       Создать catalog/rules/<n>.md
ai-dotfiles delete skill <n>      Удалить standalone скилл
ai-dotfiles delete agent <n>      Удалить standalone агент
ai-dotfiles delete rule <n>       Удалить standalone правило

# --- Домены ---

ai-dotfiles domain create <n>                Создать из _example/
ai-dotfiles domain delete <n>                Удалить целиком
ai-dotfiles domain list <n>                  Что внутри домена
ai-dotfiles domain add <n> skill <name>      Создать скилл в домене
ai-dotfiles domain add <n> agent <name>      Создать агент в домене
ai-dotfiles domain add <n> rule <name>       Создать правило в домене
ai-dotfiles domain remove <n> skill <name>   Удалить скилл из домена
ai-dotfiles domain remove <n> agent <name>   Удалить агент из домена
ai-dotfiles domain remove <n> rule <name>    Удалить правило из домена

# --- Стеки ---

ai-dotfiles stack create <n>                 Создать пустой .conf
ai-dotfiles stack delete <n>                 Удалить стек
ai-dotfiles stack list <n>                   Что в стеке
ai-dotfiles stack add <n> <items...>         Добавить элементы
ai-dotfiles stack remove <n> <items...>      Убрать элементы
ai-dotfiles stack apply <n>                  Применить к проекту (= add)

# --- Вендоринг ---

ai-dotfiles vendor <url>          Скачать стороннее в catalog/, создать .source
```

### Формат элементов

```
@domain        — домен из catalog/<domain>/
skill:name     — скилл из catalog/skills/<n>/
agent:name     — агент из catalog/agents/<n>.md
rule:name      — правило из catalog/rules/<n>.md
```

## Что делает каждая команда

### init

```bash
# В проекте — создаёт пустой манифест
ai-dotfiles init
# → ai-dotfiles.json в корне проекта (пустой, с подсказками)

# Глобально — создаёт хранилище со scaffold
ai-dotfiles init -g
# → ~/.ai-dotfiles/ со структурой, примерами, README.md
# → Линкует global/ → ~/.claude/

# Глобально — клонирует существующее
ai-dotfiles init -g --from git@github.com:user/my-ai-config.git
# → Клонирует в ~/.ai-dotfiles/
# → Линкует global/ → ~/.claude/
```

### install

```bash
# В проекте — читает ai-dotfiles.json из корня, создаёт симлинки в .claude/
cd ~/projects/my-api
ai-dotfiles install
# → Парсит ai-dotfiles.json
# → Для @domain: симлинки skills/, agents/, rules/, hooks/
# → Для skill:/agent:/rule:: симлинки standalone элементов
# → Собирает .claude/settings.json из settings.fragment.json
# → Пропускает README.md, chmod +x на .sh

# Глобально — линкует всё в ~/.claude/
ai-dotfiles install -g
# → global/CLAUDE.md → ~/.claude/CLAUDE.md
# → global/settings.json → ~/.claude/settings.json
# → global/hooks/ → ~/.claude/hooks/
# → global/output-styles/* → ~/.claude/output-styles/*
# → Читает global.json, линкует из catalog/ в ~/.claude/
# → Бэкапит конфликты в ~/.dotfiles-backup/
```

### add / remove

```bash
# Добавить к проекту
ai-dotfiles add @python skill:code-review agent:researcher
# → Дописывает в ai-dotfiles.json
# → Создаёт симлинки
# → Пересобирает settings.json

# Добавить глобально
ai-dotfiles add -g skill:web-research
# → Дописывает в global.json
# → Симлинкает в ~/.claude/skills/

# Убрать из проекта
ai-dotfiles remove @python
# → Удаляет из ai-dotfiles.json
# → Удаляет симлинки
# → Пересобирает settings.json
```

### stack apply

```bash
ai-dotfiles stack apply backend
# → Читает stacks/backend.conf
# → Вызывает add для каждого элемента
# → Записывает "stack": "backend" в ai-dotfiles.json
```

### vendor

```bash
ai-dotfiles vendor https://github.com/user/repo/tree/main/skills/frontend-design
# → Скачивает в catalog/skills/frontend-design/
# → Создаёт .source (origin, fetched, license)
# → НЕ добавляет никуда автоматически
# → "Готово. Используй: ai-dotfiles add skill:frontend-design"
```

### domain — управление доменами

```bash
ai-dotfiles domain create python
# → catalog/python/{skills/, agents/, rules/, hooks/, settings.fragment.json}
# → Все файлы — заготовки из _example/ с YAML-референсами

ai-dotfiles domain list python
# → skills: (пусто)
# → agents: (пусто)
# → rules:  (пусто)
# → hooks:  (пусто)

ai-dotfiles domain add python skill py-lint
# → catalog/python/skills/py-lint/SKILL.md (шаблон)

ai-dotfiles domain add python agent py-debug
# → catalog/python/agents/py-debug.md (шаблон)

ai-dotfiles domain add python rule py-style
# → catalog/python/rules/py-style.md (шаблон)

ai-dotfiles domain remove python skill py-lint
# → Удаляет catalog/python/skills/py-lint/

ai-dotfiles domain delete python
# → Удаляет catalog/python/ целиком
# → Предупреждает если используется в ai-dotfiles.json или стеках
```

### stack — управление стеками

```bash
ai-dotfiles stack create backend
# → stacks/backend.conf (пустой с подсказками)

ai-dotfiles stack add backend @python skill:code-review agent:researcher
# → Дописывает в stacks/backend.conf

ai-dotfiles stack list backend
# → @python
# → skill:code-review
# → agent:researcher

ai-dotfiles stack remove backend @python
# → Убирает из stacks/backend.conf

ai-dotfiles stack delete backend
# → Удаляет stacks/backend.conf
```

### create / delete — standalone элементы

```bash
ai-dotfiles create skill my-linter     # → catalog/skills/my-linter/SKILL.md
ai-dotfiles create agent debugger      # → catalog/agents/debugger.md
ai-dotfiles create rule testing        # → catalog/rules/testing.md

ai-dotfiles delete skill my-linter     # удалить из catalog/skills/
ai-dotfiles delete agent debugger      # удалить из catalog/agents/
ai-dotfiles delete rule testing        # удалить из catalog/rules/
# → Предупреждает если используется в ai-dotfiles.json или стеках
```

Все шаблоны содержат полные YAML-референсы в комментариях —
не нужно лезть в документацию чтобы вспомнить frontmatter.


## Полный флоу

### Первая машина

```bash
# 1. Установить CLI (brew install ai-dotfiles / pipx / бинарник из releases)

# 2. Создать хранилище
ai-dotfiles init -g
# Отредактировать ~/.ai-dotfiles/global/CLAUDE.md и settings.json

# 3. Добавить universal скиллы глобально
ai-dotfiles add -g skill:web-research agent:summarizer

# 4. Наполнить каталог
ai-dotfiles domain create python
ai-dotfiles domain add python skill py-conventions
ai-dotfiles domain add python agent py-debug
# Отредактировать содержимое скиллов/агентов
ai-dotfiles create skill code-review
# Отредактировать catalog/skills/code-review/SKILL.md

# 5. Закоммитить хранилище
cd ~/.ai-dotfiles && git init && git add -A && git commit -m "initial"
git remote add origin git@github.com:user/my-ai-config.git && git push

# 6. Настроить проект
cd ~/projects/my-api
ai-dotfiles init
ai-dotfiles stack apply backend
# или вручную:
ai-dotfiles add @python skill:code-review agent:researcher

# 7. Закоммитить ai-dotfiles.json в проект
git add ai-dotfiles.json && git commit -m "ai-dotfiles: add packages"
```

### Вторая машина

```bash
# 1. Установить CLI (brew install ai-dotfiles / pipx / бинарник из releases)

# 2. Клонировать хранилище
ai-dotfiles init -g --from git@github.com:user/my-ai-config.git

# 3. Клонировать проект и установить зависимости
git clone git@github.com:user/my-api.git
cd my-api
ai-dotfiles install
# → Читает ai-dotfiles.json → всё на месте
```

## Путь к хранилищу

По умолчанию: `~/.ai-dotfiles/`

Переопределить через переменную окружения:

```bash
# В .zshrc / .bashrc
export AI_DOTFILES_HOME=~/custom/path
```

Никаких конфиг-файлов CLI — одна переменная, один дефолт.

---

## Хранилище: структура scaffold

Генерируется при `ai-dotfiles init -g`:

```
~/.ai-dotfiles/
│
├── global/                             # → ~/.claude/
│   ├── README.md                       # Что тут, порог входа, ссылки на docs
│   ├── CLAUDE.md                       # Глобальные инструкции (< 100 строк)
│   ├── settings.json                   # Permissions, env, глобальные hooks
│   ├── hooks/
│   │   ├── README.md                   # События, matchers, handlers, скоупы
│   │   ├── post-edit-lint.sh
│   │   └── pre-commit-check.sh
│   └── output-styles/
│       ├── README.md                   # Формат, встроенные стили
│       └── concise-ru.md
│   # skills/ и agents/ появляются через ai-dotfiles add -g
│
├── global.json                     # Манифест глобальных элементов из catalog/
│
├── catalog/
│   ├── README.md                       # Структура, форматы, вендоринг
│   │
│   ├── _example/                       # Образцовый домен
│   │   ├── skills/example-skill/
│   │   │   ├── SKILL.md                # Полный YAML frontmatter
│   │   │   ├── scripts/check.sh
│   │   │   └── references/cheatsheet.md
│   │   ├── agents/example-agent.md     # Полный YAML frontmatter
│   │   ├── rules/example-style.md      # Scoped rule с paths:
│   │   ├── hooks/example-lint.sh       # jq + exit codes
│   │   └── settings.fragment.json      # Хук-декларации
│   │
│   ├── skills/                         # Standalone скиллы
│   │   ├── git-workflow/SKILL.md
│   │   ├── code-review/SKILL.md
│   │   └── infra-debug/
│   │       ├── SKILL.md
│   │       └── scripts/check-xray.sh
│   │
│   ├── agents/                         # Standalone агенты
│   │   ├── researcher.md
│   │   ├── reviewer.md
│   │   └── architect.md
│   │
│   └── rules/                          # Standalone правила
│       ├── code-style.md
│       ├── security.md
│       └── communication.md
│
├── stacks/
│   ├── README.md                       # Формат .conf
│   └── _example.conf
│
└── README.md                           # Архитектура, quick start
```

### README.md в каждой папке

Содержат:
- Ссылки на официальную документацию Claude Code
- Полные YAML-референсы деклараций (frontmatter скиллов, агентов, rules, хуков)
- Примеры

### settings.fragment.json

```json
{
  "_domain": "python",
  "_description": "Ruff format for .py files",
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "if": "Edit(*.py)|Write(*.py)",
        "type": "command",
        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/ruff-on-save.sh"
      }]
    }]
  }
}
```

### stacks/ формат

```bash
# stacks/_example.conf
# По строке на элемент, # — комментарий
@_example
skill:git-workflow
agent:reviewer
rule:code-style
```

### Вендоринг

```bash
ai-dotfiles vendor https://github.com/user/repo/tree/main/skills/frontend-design
# → catalog/skills/frontend-design/
# → catalog/skills/frontend-design/.source

# Или вручную из любого источника:
npx skills add vercel-labs/agent-skills --skill frontend-design -g
cp -r ~/.agents/skills/frontend-design ~/.ai-dotfiles/catalog/skills/
```

`.source` файл:

```
origin: github:vercel-labs/agent-skills/skills/frontend-design
fetched: 2026-04-15
tool: npx skills add
license: Apache-2.0
```

---

## Задача для Claude Code

### Промпт 1: CLI-тул

```
Создай CLI-тул ai-dotfiles для управления
конфигурацией Claude Code. Работает как пакетный менеджер.

Язык реализации — на усмотрение (Go, Python, Rust, etc.).
Внешних runtime-зависимостей быть не должно (no jq, no Node.js at runtime).
Дистрибуция: единый бинарник или пакет без тяжёлого рантайма.

Конфиг: нет файла. Путь к хранилищу:
  AI_DOTFILES_HOME (env var), дефолт ~/.ai-dotfiles/

Хранилище по умолчанию: ~/.ai-dotfiles/

Формат элементов:
  @domain     — catalog/<domain>/
  skill:name  — catalog/skills/<n>/
  agent:name  — catalog/agents/<n>.md
  rule:name   — catalog/rules/<n>.md

Манифест проекта: ai-dotfiles.json в корне проекта (JSON)
Манифест глобальный: <storage>/global.json

Команды:

  init              — создать ai-dotfiles.json в корне проекта (JSON)
  init -g           — создать хранилище со scaffold, линковать global/
  init -g --from <url> — клонировать хранилище, линковать global/

  install           — прочитать ai-dotfiles.json, создать симлинки,
                      собрать settings.json из settings.fragment.json
  install -g        — линковать global/ → ~/.claude/ поэлементно
                      (CLAUDE.md, settings.json, hooks/, output-styles/),
                      прочитать global.json, линковать из catalog/

  add <items...>    — дописать в ai-dotfiles.json + создать симлинки
                      + пересобрать settings.json
  add -g <items...> — дописать в global.json + линковать в ~/.claude/

  remove <items...>    — убрать из packages + удалить симлинки
  remove -g <items...> — убрать из global.json + удалить из ~/.claude/


  list              — содержимое ai-dotfiles.json
  list -g           — содержимое global.json
  list --available  — всё в catalog/ и stacks/

  status            — валидировать симлинки, показать merged hooks
  vendor <url>      — скачать в catalog/, создать .source

  create skill <n>  — standalone скилл в catalog/skills/
  create agent <n>  — standalone агент в catalog/agents/
  create rule <n>   — standalone правило в catalog/rules/
  delete skill|agent|rule <n> — удалить standalone элемент

  domain create <n>              — scaffold catalog/<n>/ из _example/
  domain delete <n>              — удалить домен целиком
  domain list <n>                — содержимое домена
  domain add <n> skill|agent|rule <n>   — создать элемент в домене
  domain remove <n> skill|agent|rule <n> — удалить элемент из домена

  stack create <n>               — создать пустой .conf
  stack delete <n>               — удалить стек
  stack list <n>                 — содержимое стека
  stack add <n> <items...>       — добавить элементы в стек
  stack remove <n> <items...>    — убрать элементы из стека
  stack apply <n>                — применить к проекту (= add для каждого)


При линковке:
  - safe_symlink(): бэкап конфликтов в ~/.dotfiles-backup/
  - Пропуск README.md
  - chmod +x на .sh файлы
  - @domain: симлинки skills/, agents/, rules/, hooks/
  - Идемпотентность

Сборка settings.json: deep merge массивов хуков по событиям
из settings.fragment.json всех подключённых доменов.
Поля _domain, _description удаляются.

Scaffold при init -g: генерировать структуру хранилища
с README.md, _example/, заготовками global/ и stacks/.
Содержимое scaffold — из отдельного шаблона (см. промпт 2).

Scaffold шаблоны для create: каждый шаблон содержит
полный YAML frontmatter в комментариях как референс,
чтобы не лезть в документацию.

Тесты: smoke test для init, add, remove, install, create, delete, stack, status.
README.md: установка, quick start, все команды, примеры.
```

### Промпт 2: Scaffold хранилища

```
Создай шаблон хранилища ai-dotfiles — структуру,
которую CLI генерирует при `ai-dotfiles init -g`.

1. global/README.md:
   - Таблица содержимого, порог входа (нужно в КАЖДОЙ сессии)
   - Ссылки: claude-directory, settings, hooks-guide, hooks,
     memory, best-practices, output-styles

2. global/CLAUDE.md (< 100 строк):
   - Русский для ответов, английский для кода
   - Лаконичные ответы
   - git diff --staged перед коммитом

3. global/settings.json:
   - allow: Bash(git *), Bash(npm run *), Bash(docker *)
   - deny: Read(.env), Read(.env.*), Read(secrets/**)
   - hooks: PostToolUse Edit|Write, PreToolUse Bash(git commit *)

4. global/hooks/:
   - README.md: события, matchers, handlers, скоупы, ссылки
   - post-edit-lint.sh и pre-commit-check.sh (chmod +x)

5. global/output-styles/:
   - README.md: формат, встроенные стили
   - concise-ru.md

6. global.json: { "packages": [] } — пустой, готовый к add -g

7. catalog/README.md:
   - Структура домена, формат ai-dotfiles.json,
     формат settings.fragment.json, вендоринг, ссылки на docs

8. catalog/_example/: полный образцовый домен
   - skills/example-skill/SKILL.md (полный YAML frontmatter)
   - agents/example-agent.md (полный YAML frontmatter)
   - rules/example-style.md (scoped rule с paths:)
   - hooks/example-lint.sh (jq + exit codes)
   - settings.fragment.json

9. catalog/skills/:
   - git-workflow/SKILL.md, code-review/SKILL.md

10. catalog/agents/:
    - researcher.md, reviewer.md, architect.md

11. catalog/rules/:
    - code-style.md, security.md, communication.md

12. stacks/:
    - README.md: формат .conf
    - _example.conf

13. README.md: архитектура, quick start, shell-алиасы
14. .gitignore: *.local.*, .dotfiles-backup/
```

---

## Vendor plugins

Третьесторонний контент попадает в каталог через *vendor-плагины* —
модули, знающие как общаться с одним источником (GitHub, upstream
npm-CLI `skills`, и т.д.). Каркас общий, плагин тонкий.

### Registry

Плагины живут в `src/ai_dotfiles/vendors/` и регистрируются как
module-level singleton'ы в `vendors/__init__.py`:

```python
# src/ai_dotfiles/vendors/__init__.py
REGISTRY: dict[str, Vendor] = {
    "github": cast(Vendor, GITHUB),
    "skills_sh": cast(Vendor, SKILLS_SH),
    "paks": cast(Vendor, PAKS),
}
```

CLI-слой (`commands/vendor.py`) динамически собирает поддерево
`ai-dotfiles vendor <name> {install, list, deps}` из содержимого
`REGISTRY`. Чтобы добавить новый vendor, достаточно реализовать
`Vendor`-протокол и дописать запись в реестр — CLI ничего менять не
нужно.

### Protocol

```python
# src/ai_dotfiles/vendors/base.py
@runtime_checkable
class Vendor(Protocol):
    name: str
    display_name: str
    description: str
    deps: tuple[Dependency, ...]

    def list_source(self, source: str) -> Iterable[str]: ...
    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]: ...
```

- `list_source(source)` — перечислить элементы источника без скачивания.
- `fetch(source, select, workdir)` — подготовить содержимое в
  `workdir/` и вернуть список `FetchedItem(kind, name, source_dir,
  origin, license)`. Сам плагин не пишет в каталог — это делает
  shared-сервис `placement`.
- `deps` — кортеж объектов `Dependency(name, check, install_cmd,
  manual_hint)`, описывающих runtime-требования плагина (см. ниже).

### Shared services

Код плагинов остаётся маленьким за счёт разделяемой инфраструктуры:

- **`source_file`** — пишет/читает `.source` (`vendor`, `origin`,
  `tool`, `fetched`, `license`). Формат одинаков для всех плагинов.
- **`placement`** — `place_item(item, catalog_root, force,
  vendor_name)` переносит `source_dir` в
  `catalog/<kind>s/<name>/`, затем дропает `.source` рядом.
- **`deps`** — `check`/`ensure`/`install` для списка `Dependency`;
  умеет подсказать пользователю ручную инструкцию, предложить
  платформо-специфичный `install_cmd`, защищается от отсутствия
  Homebrew и не запускает `sudo` сам.

### Как добавить новый vendor

1. Создать модуль `src/ai_dotfiles/vendors/<name>.py`:
   - Объявить `Dependency`-объекты (через `shutil.which` и
     платформенные install-команды).
   - Реализовать frozen dataclass с методами `list_source` и `fetch`.
   - Экспонировать module-level singleton (`MY_VENDOR = _MyVendor()`).
2. В `vendors/__init__.py` добавить запись в `REGISTRY`:
   ```python
   REGISTRY: dict[str, Vendor] = {
       "github": cast(Vendor, GITHUB),
       "skills_sh": cast(Vendor, SKILLS_SH),
       "<name>": cast(Vendor, MY_VENDOR),
   }
   ```
3. Покрыть unit-тестами (`tests/unit/`) и e2e-тестами
   (`tests/e2e/test_vendor_<name>.py`). CLI-команды появятся
   автоматически после регистрации.

### Opt-in runtime dependencies

Ядро CLI не имеет внешних runtime-зависимостей (только чистый Python
>=3.12). Требования подключают только сами плагины:

- `vendor github` → `git` на `PATH`.
- `vendor skills_sh` → Node.js / `npx` на `PATH`.
- `vendor paks` → нативный бинарник `paks` (Rust, см.
  <https://paks.stakpak.dev>; macOS: `brew tap stakpak/stakpak && brew
  install paks`). Установка out-of-band — CLI только проверяет
  присутствие на `PATH`.

Пользователь ставит зависимость вручную по ссылке, которую покажет
`ai-dotfiles vendor <name> deps check`. Неиспользуемые vendor-плагины
ничего не требуют и не ломают запуск CLI без сетевого доступа.

## Заметки

- **CLI open source, хранилище приватное**: тул на GitHub, конфигурация в приватном репо
- **Как npm**: manifest (ai-dotfiles.json) + install = воспроизводимость
- **-g флаг**: без него — проект (.claude/), с ним — глобальный (~/.claude/)
- **global/ — минимум**: CLAUDE.md, settings.json, hooks/, output-styles/. Skills/agents появляются через `add -g`
- **catalog/ — всё подключаемое**: домены и standalone, своё и вендорённое
- **Вендоринг**: `vendor <url>` или вручную. Коммитится в хранилище, git контролирует версии
- **stacks/ — пресеты**: `ai-dotfiles stack apply backend` = `add` для списка элементов
- **settings.json собирается**: глобальный в global/ — базовый; проектный — merge фрагментов доменов
- **Hooks vs Rules**: hook = 100%; rule = ~80%
- **Одинаковые пути**: `~/projects/<repo>` на всех машинах для `claude --resume`
