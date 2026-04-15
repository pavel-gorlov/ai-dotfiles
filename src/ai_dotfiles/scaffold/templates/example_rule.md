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
