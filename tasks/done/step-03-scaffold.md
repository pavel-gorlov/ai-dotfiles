# Step 3: Scaffold templates + generator

## Goal

Create all template files for storage scaffold (`ai-dotfiles init -g`) and element creation templates (`create skill/agent/rule`). Build the generator that assembles the directory tree from templates.

## Part A: Template files

All files go in `src/ai_dotfiles/scaffold/templates/`. They are included as package data.

### `global_readme.md`

README for `~/.ai-dotfiles/global/` directory. Contains:
- Table: what each file does (CLAUDE.md, settings.json, hooks/, output-styles/)
- Note: "Loaded in EVERY Claude Code session"
- Links to docs:
  - https://docs.anthropic.com/en/docs/claude-code/settings#claude-directory
  - https://docs.anthropic.com/en/docs/claude-code/settings
  - https://docs.anthropic.com/en/docs/claude-code/hooks
  - https://docs.anthropic.com/en/docs/claude-code/memory
  - https://docs.anthropic.com/en/docs/claude-code/best-practices
  - https://docs.anthropic.com/en/docs/claude-code/settings#output-styles

### `global_claude.md`

Default CLAUDE.md (< 100 lines):
```markdown
# Global Instructions

## Language
- Respond in Russian
- Code, variables, comments: English

## Style
- Be concise — short answers, no filler
- Lead with the answer, not the reasoning

## Git
- Always run `git diff --staged` before committing
- Write commit messages in English
```

### `global_settings.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(npm run *)",
      "Bash(docker *)"
    ],
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Read(secrets/**)"
    ]
  }
}
```

### `global_hooks_readme.md`

README for hooks/ directory. Contains:
- Hook events: PreToolUse, PostToolUse, Notification, Stop, SubagentStop
- Matcher format and examples
- Handler types: command, intercept
- Exit codes: 0=allow, 2=block with message
- Links: https://docs.anthropic.com/en/docs/claude-code/hooks

### `post_edit_lint.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook: lint files after Edit/Write
# Matcher: Edit|Write
# Runs after Claude edits any file

FILE="$TOOL_INPUT_FILE_PATH"
[[ -z "$FILE" ]] && exit 0

case "$FILE" in
  *.py) ruff check --fix "$FILE" 2>/dev/null ;;
  *.js|*.ts) npx eslint --fix "$FILE" 2>/dev/null ;;
esac
exit 0
```

### `pre_commit_check.sh`

```bash
#!/usr/bin/env bash
# PreToolUse hook: verify staged changes before git commit
# Matcher: Bash(git commit *)
# Blocks commit if there are issues

echo "Pre-commit check: reviewing staged changes..."
git diff --staged --stat
exit 0
```

### `output_styles_readme.md`

README for output-styles/. Contains:
- Format reference: markdown file with style instructions
- Built-in styles available in Claude Code
- Link: https://docs.anthropic.com/en/docs/claude-code/settings#output-styles

### `concise_ru.md`

```markdown
Respond in Russian. Be extremely concise:
- One sentence answers when possible
- No preamble or filler phrases
- Code speaks for itself — minimal commentary
- Use bullet points over paragraphs
```

### `catalog_readme.md`

README for catalog/ directory. Contains:
- Domain structure: `catalog/<domain>/{skills/, agents/, rules/, hooks/, settings.fragment.json}`
- Standalone structure: `catalog/skills/<name>/`, `catalog/agents/<name>.md`, `catalog/rules/<name>.md`
- Element format: `@domain`, `skill:name`, `agent:name`, `rule:name`
- settings.fragment.json format with example
- Vendoring: `ai-dotfiles vendor <url>`

### `example_skill.md`

Full example SKILL.md for `catalog/_example/skills/example-skill/`:

```markdown
---
name: example-skill
description: An example skill demonstrating full YAML frontmatter
# Available frontmatter fields:
#   name: string (required) — display name, used in /skill-name
#   description: string (required) — shown in skill list
#   instructions: string — detailed instructions for Claude
#   tools: list — tools this skill can use [Bash, Read, Write, Edit, ...]
#   allowed_tools: list — alias for tools
#   input: string — expected input format description
---

# Example Skill

This skill demonstrates the structure of a Claude Code skill.

## When to use

Describe when this skill should be invoked.

## Instructions

Step-by-step instructions for Claude when this skill is activated.
```

### `example_agent.md`

Full example for `catalog/_example/agents/`:

```markdown
---
name: example-agent
description: An example agent demonstrating full YAML frontmatter
model: sonnet
# Available frontmatter fields:
#   name: string (required)
#   description: string (required)
#   model: string — sonnet | opus | haiku
#   instructions: string — system prompt for the agent
#   tools: list — tools available to this agent
#   allowed_tools: list — alias for tools
---

# Example Agent

An example subagent configuration.

## Purpose

Describe what this agent specializes in.

## Instructions

You are a specialized agent that...
```

### `example_rule.md`

Full example for `catalog/_example/rules/`:

```markdown
---
name: example-style
description: Example scoped rule for code style
globs: "src/**/*.py"
# Available frontmatter fields:
#   name: string (required)
#   description: string (required)
#   globs: string | list — file patterns this rule applies to
#   alwaysApply: boolean — if true, applies regardless of file context
---

# Python Style Rule

When editing Python files in src/:

- Use type hints for all function parameters and return values
- Prefer dataclasses over plain dicts for structured data
- Use pathlib.Path instead of os.path
```

### `example_hook.sh`

```bash
#!/usr/bin/env bash
# Example PostToolUse hook for domain "_example"
# Triggered after Edit or Write on files matching the domain
#
# Available environment variables:
#   TOOL_NAME        — name of the tool that was used
#   TOOL_INPUT_*     — tool input parameters (e.g. TOOL_INPUT_FILE_PATH)
#   TOOL_OUTPUT_*    — tool output (e.g. TOOL_OUTPUT_CONTENT)
#   CLAUDE_PROJECT_DIR — project root

FILE="$TOOL_INPUT_FILE_PATH"
[[ -z "$FILE" ]] && exit 0

echo "Example hook: processed $FILE"
exit 0
```

### `example_settings_fragment.json`

```json
{
  "_domain": "_example",
  "_description": "Example domain hooks — edit or remove",
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/example-lint.sh"
      }]
    }]
  }
}
```

### `stacks_readme.md`

README for stacks/. Contains:
- Format: one element per line, `#` for comments
- Example .conf content
- Usage: `ai-dotfiles stack apply <name>`

### `example_stack.conf`

```
# Example stack — apply with: ai-dotfiles stack apply _example
# One element per line. Lines starting with # are comments.
@_example
skill:git-workflow
agent:reviewer
rule:code-style
```

### `root_readme.md`

Root README.md for `~/.ai-dotfiles/`:
- What is this directory
- Quick start (3 steps)
- Directory structure overview
- Shell aliases suggestion: `alias adf='ai-dotfiles'`

### `gitignore`

```
*.local.*
.dotfiles-backup/
```

### `skill_template.md`

Template for `ai-dotfiles create skill <name>`:

```markdown
---
name: {{name}}
description: TODO — describe this skill
# Available frontmatter fields:
#   name: string (required) — display name, used in /skill-name
#   description: string (required) — shown in skill list
#   instructions: string — detailed instructions for Claude
#   tools: list — tools this skill can use
#   input: string — expected input format
---

# {{name}}

TODO — describe what this skill does and when to use it.
```

### `agent_template.md`

```markdown
---
name: {{name}}
description: TODO — describe this agent
model: sonnet
# Available frontmatter fields:
#   name: string (required)
#   description: string (required)
#   model: string — sonnet | opus | haiku
#   instructions: string — system prompt
#   tools: list — available tools
---

# {{name}}

TODO — describe this agent's purpose and capabilities.
```

### `rule_template.md`

```markdown
---
name: {{name}}
description: TODO — describe this rule
globs: "**/*"
# Available frontmatter fields:
#   name: string (required)
#   description: string (required)
#   globs: string | list — file patterns
#   alwaysApply: boolean — always active regardless of context
---

# {{name}}

TODO — describe the coding rules and conventions.
```

## Part B: Generator

### File: `src/ai_dotfiles/scaffold/generator.py`

```python
from pathlib import Path
from importlib import resources

def _read_template(name: str) -> str:
    """Read template file from package data."""

def _write_template(name: str, dest: Path, replacements: dict[str, str] | None = None) -> None:
    """Read template file, apply {{key}} replacements, write to dest.
    Set chmod +x if dest ends with .sh."""

def generate_storage_scaffold(root: Path) -> None:
    """Create full storage directory structure at root.
    
    Creates:
      root/
      ├── global/
      │   ├── README.md          <- global_readme.md
      │   ├── CLAUDE.md          <- global_claude.md
      │   ├── settings.json      <- global_settings.json
      │   ├── hooks/
      │   │   ├── README.md      <- global_hooks_readme.md
      │   │   ├── post-edit-lint.sh    <- post_edit_lint.sh
      │   │   └── pre-commit-check.sh <- pre_commit_check.sh
      │   └── output-styles/
      │       ├── README.md      <- output_styles_readme.md
      │       └── concise-ru.md  <- concise_ru.md
      ├── global.json            <- {"packages": []}
      ├── catalog/
      │   ├── README.md          <- catalog_readme.md
      │   ├── _example/
      │   │   ├── skills/example-skill/SKILL.md  <- example_skill.md
      │   │   ├── agents/example-agent.md        <- example_agent.md
      │   │   ├── rules/example-style.md         <- example_rule.md
      │   │   ├── hooks/example-lint.sh          <- example_hook.sh
      │   │   └── settings.fragment.json         <- example_settings_fragment.json
      │   ├── skills/            (empty dir)
      │   ├── agents/            (empty dir)
      │   └── rules/             (empty dir)
      ├── stacks/
      │   ├── README.md          <- stacks_readme.md
      │   └── _example.conf      <- example_stack.conf
      ├── README.md              <- root_readme.md
      └── .gitignore             <- gitignore
    """

def generate_project_manifest(root: Path) -> None:
    """Create ai-dotfiles.json with empty packages list.
    
    Content: {"packages": []}
    Does NOT overwrite if file already exists.
    """

def generate_element_from_template(
    element_type: str,  # "skill", "agent", "rule"
    name: str,
    dest: Path,
) -> Path:
    """Create a new element from template.
    
    skill -> dest/SKILL.md from skill_template.md
    agent -> dest (the .md file itself) from agent_template.md
    rule  -> dest (the .md file itself) from rule_template.md
    
    Applies {{name}} replacement.
    Returns path of created file.
    """
```

### pyproject.toml update

Add to `pyproject.toml`:
```toml
[tool.setuptools.package-data]
ai_dotfiles = ["scaffold/templates/*"]
```

## Tests

File: `tests/test_scaffold.py`

1. `test_generate_storage_scaffold` — creates all expected dirs and files
2. `test_generate_storage_scaffold_files_not_empty` — template content is written
3. `test_generate_storage_scaffold_sh_executable` — .sh files have +x
4. `test_generate_project_manifest` — creates ai-dotfiles.json with correct content
5. `test_generate_project_manifest_no_overwrite` — doesn't overwrite existing file
6. `test_generate_element_skill` — creates skills/<name>/SKILL.md with name replaced
7. `test_generate_element_agent` — creates agents/<name>.md
8. `test_generate_element_rule` — creates rules/<name>.md
9. `test_templates_loadable` — all template files accessible via importlib.resources

## Definition of Done

- [ ] All template files exist in `src/ai_dotfiles/scaffold/templates/`
- [ ] `src/ai_dotfiles/scaffold/generator.py` exists with all functions
- [ ] `tests/integration/test_scaffold.py` exists with all 9 test cases
- [ ] `poetry run pytest tests/integration/test_scaffold.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/scaffold/generator.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Templates loadable via `importlib.resources` (test_templates_loadable)
- [ ] .sh templates get chmod +x after generation
- [ ] `{{name}}` placeholders replaced in element templates
- [ ] `pyproject.toml` declares package data for templates

## Commit message

`feat: scaffold templates and generator for init -g and create commands`
