# Step 8: commands/vendor.py

## Goal

Implement `ai-dotfiles vendor <url>` — download external content from GitHub into catalog/ and create a `.source` tracking file.

## File: `src/ai_dotfiles/commands/vendor.py`

### Command definition

```python
@click.command()
@click.argument("url")
def vendor(url: str) -> None:
    """Download external content into catalog/."""
```

### Behavior

1. Parse URL via `git_ops.parse_github_url(url)`
   - If not recognized, error with supported formats
2. Determine destination:
   - Detect element type from URL path or downloaded content
   - Skills go to `catalog/skills/<name>/`
   - Agents go to `catalog/agents/<name>.md` (or dir)
   - Rules go to `catalog/rules/<name>.md` (or dir)
   - If unclear, default to `catalog/skills/<name>/`
3. Check destination doesn't exist — error if it does (use `--force` to overwrite)
4. Download via `git_ops.git_sparse_checkout(repo_url, subpath, dest)`
5. Create `.source` file in dest:

```
origin: github:<user>/<repo>/<subpath>
fetched: 2026-04-15
tool: ai-dotfiles vendor
license: unknown
```

6. Print:
```
Downloaded to catalog/skills/frontend-design/
Source tracked in .source

Ready to use:
  ai-dotfiles add skill:frontend-design
```

### URL formats supported

```
# GitHub tree URL (specific dir)
https://github.com/user/repo/tree/main/skills/frontend-design

# GitHub repo root (clones entire repo as a domain)
https://github.com/user/repo

# SSH
git@github.com:user/repo.git
```

### .source file format

```
origin: github:user/repo/path/to/content
fetched: 2026-04-15
tool: ai-dotfiles vendor
license: unknown
```

Simple key-value, one per line. Not JSON — easier to read/edit.

## File: `tests/test_vendor.py`

1. `test_vendor_github_tree` — downloads to correct location (mocked git)
2. `test_vendor_creates_source_file` — .source exists with correct content
3. `test_vendor_destination_exists` — error
4. `test_vendor_invalid_url` — error with helpful message
5. `test_vendor_print_next_steps` — output contains "ai-dotfiles add" hint
6. `test_vendor_source_file_format` — correct key-value format and date

## Dependencies

- `core.git_ops`
- `core.paths`
- `ui`

## Definition of Done

- [ ] `src/ai_dotfiles/commands/vendor.py` exists with vendor command
- [ ] `tests/e2e/test_vendor.py` exists with all 6 test cases
- [ ] `poetry run pytest tests/e2e/test_vendor.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/vendor.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] .source file created with correct format (origin, fetched, tool, license)
- [ ] Git operations mocked in tests (no real network)
- [ ] Output includes "ai-dotfiles add" hint for next step

## Commit message

`feat: vendor command — download external content with source tracking`
