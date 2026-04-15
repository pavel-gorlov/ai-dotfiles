# Step 7a: commands/list_cmd.py

## Goal

Implement `ai-dotfiles list`, `list -g`, and `list --available`.

## File: `src/ai_dotfiles/commands/list_cmd.py`

### Command definition

```python
@click.command("list")
@click.option("-g", "--global", "is_global", is_flag=True)
@click.option("--available", is_flag=True, help="Show all items in catalog and stacks")
def list_cmd(is_global: bool, available: bool) -> None:
```

Note: named `list_cmd` to avoid shadowing Python's `list` builtin. Registered as `"list"` in click.

### Behavior: `ai-dotfiles list`

1. Find project root, read ai-dotfiles.json
2. Group packages by type (domains, skills, agents, rules)
3. Print grouped list

Output:
```
Packages (ai-dotfiles.json):

  Domains:
    @python
    @telegram-api

  Skills:
    skill:code-review
    skill:git-workflow

  Agents:
    agent:researcher

  Rules:
    rule:security
```

If empty: `No packages installed.`

### Behavior: `ai-dotfiles list -g`

Same but reads `global.json`.

### Behavior: `ai-dotfiles list --available`

1. Scan `catalog/` for:
   - Domains: dirs in `catalog/` (skip `_example`, `skills`, `agents`, `rules`)
   - Standalone skills: dirs in `catalog/skills/`
   - Standalone agents: .md files in `catalog/agents/`
   - Standalone rules: .md files in `catalog/rules/`
2. Scan `stacks/` for .conf files
3. Print everything grouped

Output:
```
Available in catalog:

  Domains:
    @python
    @go

  Skills:
    skill:code-review
    skill:git-workflow
    skill:infra-debug

  Agents:
    agent:researcher
    agent:reviewer
    agent:architect

  Rules:
    rule:code-style
    rule:security
    rule:communication

Stacks:
    backend
    frontend
```

## File: `tests/test_list.py`

1. `test_list_project_with_packages` — shows grouped packages
2. `test_list_project_empty` — shows "No packages installed"
3. `test_list_global` — reads global.json
4. `test_list_available_domains` — finds domains in catalog
5. `test_list_available_standalone` — finds skills/agents/rules
6. `test_list_available_stacks` — finds .conf files
7. `test_list_available_skips_example` — _example not shown

## Definition of Done

- [ ] `src/ai_dotfiles/commands/list_cmd.py` exists
- [ ] `tests/e2e/test_list_status.py` exists with all 7 list test cases
- [ ] `poetry run pytest tests/e2e/test_list_status.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/list_cmd.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] `list` groups packages by type
- [ ] `list --available` scans catalog/ and stacks/
- [ ] `_example` domain not shown in `--available`

## Commit

Part of batch commit after all Step 7 sub-tasks complete.
