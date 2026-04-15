# Step 7d: commands/domain.py

## Goal

Implement the `ai-dotfiles domain` subcommand group: create, delete, list, add, remove.

## File: `src/ai_dotfiles/commands/domain.py`

### Command group

```python
@click.group()
def domain():
    """Manage domains in catalog/."""
```

### Subcommands

#### `ai-dotfiles domain create <name>`

```python
@domain.command()
@click.argument("name")
def create(name: str) -> None:
```

1. Check `catalog/<name>/` doesn't exist
2. Create directory structure:
   ```
   catalog/<name>/
   ├── skills/
   ├── agents/
   ├── rules/
   ├── hooks/
   └── settings.fragment.json
   ```
3. `settings.fragment.json` from template with `_domain` set to `<name>`
4. Print: `Created domain @<name> at catalog/<name>/`

#### `ai-dotfiles domain delete <name>`

```python
@domain.command()
@click.argument("name")
def delete(name: str) -> None:
```

1. Check exists
2. Prevent deleting `_example`
3. Check usage (reuse `find_usage` from create_delete.py) — warn if `@<name>` is in any manifest or stack
4. Confirm deletion
5. `shutil.rmtree(catalog/<name>/)`
6. Print: `Deleted domain @<name>`

#### `ai-dotfiles domain list <name>`

```python
@domain.command("list")
@click.argument("name")
def list_domain(name: str) -> None:
```

1. Check exists
2. Scan subdirs and print contents:

```
Domain @python:
  skills:
    py-lint
    py-conventions
  agents:
    py-debug
  rules:
    (empty)
  hooks:
    ruff-on-save.sh
  settings.fragment.json: yes
```

#### `ai-dotfiles domain add <name> skill|agent|rule <element_name>`

```python
@domain.command("add")
@click.argument("name")
@click.argument("element_type", type=click.Choice(["skill", "agent", "rule"]))
@click.argument("element_name")
def add_element(name: str, element_type: str, element_name: str) -> None:
```

1. Check domain exists
2. Determine path:
   - skill: `catalog/<name>/skills/<element_name>/SKILL.md`
   - agent: `catalog/<name>/agents/<element_name>.md`
   - rule: `catalog/<name>/rules/<element_name>.md`
3. Check element doesn't exist yet
4. Create from template (reuse `generate_element_from_template`)
5. Print: `Created skill <element_name> in domain @<name>`

#### `ai-dotfiles domain remove <name> skill|agent|rule <element_name>`

```python
@domain.command("remove")
@click.argument("name")
@click.argument("element_type", type=click.Choice(["skill", "agent", "rule"]))
@click.argument("element_name")
def remove_element(name: str, element_type: str, element_name: str) -> None:
```

1. Check domain and element exist
2. Delete element (rmtree for skill dir, unlink for agent/rule)
3. Print: `Removed skill <element_name> from domain @<name>`

### Register in cli.py

```python
from ai_dotfiles.commands.domain import domain
cli.add_command(domain)
```

## File: `tests/test_domain.py`

1. `test_domain_create` — creates correct directory structure
2. `test_domain_create_already_exists` — error
3. `test_domain_create_settings_fragment` — has correct _domain value
4. `test_domain_delete` — removes directory
5. `test_domain_delete_example_blocked` — can't delete _example
6. `test_domain_delete_warns_usage` — warns if @domain in manifest
7. `test_domain_list` — shows contents grouped by type
8. `test_domain_list_empty` — shows (empty) for all categories
9. `test_domain_list_not_found` — error for missing domain
10. `test_domain_add_skill` — creates skill in domain
11. `test_domain_add_agent` — creates agent in domain
12. `test_domain_add_rule` — creates rule in domain
13. `test_domain_add_already_exists` — error
14. `test_domain_remove_skill` — deletes skill from domain
15. `test_domain_remove_not_found` — error

## Definition of Done

- [ ] `src/ai_dotfiles/commands/domain.py` exists with all 5 subcommands
- [ ] `tests/e2e/test_domain.py` exists with all 15 test cases
- [ ] `poetry run pytest tests/e2e/test_domain.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/domain.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] domain create generates correct directory structure + settings.fragment.json
- [ ] domain delete blocks deletion of `_example`
- [ ] domain add creates elements from templates with name substitution
- [ ] domain list shows contents grouped by type

## Commit

Part of batch commit after all Step 7 sub-tasks complete.
