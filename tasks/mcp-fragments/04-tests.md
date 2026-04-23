# Subtask 04: integration + e2e tests

All of subtask 01/02/03 is in place. Now we verify behavior end-to-end.

## Goal

Prove the full `add`/`remove` loop for a domain carrying an
`mcp.fragment.json` works as specified: `.mcp.json` is created /
updated / deleted; ownership file mirrors the domain-owned set;
`settings.json` gets correct `mcp__*__*` permissions and
`enabledMcpjsonServers` entries; user-authored `.mcp.json` content
survives; warnings fire for missing env vars and missing npm deps.

## File scope (exclusive)

- `tests/integration/test_mcp_add_remove.py`   (new)
- `tests/e2e/test_mcp_cli.py`                  (new)

## Do NOT touch

- Any source under `src/` — frozen.
- Any existing test file.
- `conftest.py` — reuse existing fixtures; if a new fixture is needed,
  define it locally at the top of the new test file.

## Hard rules

- Use `tmp_path`, `monkeypatch` env vars for `HOME` / `AI_DOTFILES_HOME`.
- Never touch real `~/.ai-dotfiles/` or `~/.claude/`.
- Mirror fixture patterns from `tests/integration/test_add_remove.py`
  (populated catalog with a synthetic domain).
- Use `click.testing.CliRunner` for the e2e test.
- Each test focused on one assertion family — no all-in-one mega test.
- Mark integration tests with `@pytest.mark.integration`.

## Fixture — synthetic domain with MCP fragment

Reuse the existing `catalog` fixture approach; add a new local fixture
or extend the catalog factory with an MCP-enabled domain:

```python
def _seed_mcp_domain(catalog: Path, name: str = "mcptest") -> Path:
    domain = catalog / name
    domain.mkdir(parents=True)
    (domain / "mcp.fragment.json").write_text(
        json.dumps(
            {
                "_domain": name,
                "_description": "Test MCP domain",
                "mcpServers": {
                    f"{name}-server": {
                        "command": "echo",
                        "args": ["hi"],
                        "env": {"FOO": "${TEST_MCP_FOO}"},
                    }
                },
                "_requires": {"npm": [f"@test/{name}"]},
            },
            indent=2,
        )
        + "\n"
    )
    return domain
```

(Do NOT include a `settings.fragment.json` on this domain unless a
specific test needs one — keeps assertions focused on MCP-only
behavior.)

## Tests — `tests/integration/test_mcp_add_remove.py`

### Add-side

- `test_add_writes_mcp_json`
- `test_add_injects_mcp_permissions_into_settings`
- `test_add_populates_enabled_mcpjson_servers_with_domain_owned_only`
- `test_add_preserves_user_entries_in_enabled_mcpjson_servers` —
  seed `settings.json` with `enabledMcpjsonServers: ["user-srv"]`
  before `add`; post-add list contains both.
- `test_add_preserves_user_authored_mcp_server` —
  seed `.mcp.json` with `{"mcpServers": {"user-srv": {...}}}` before
  `add`; post-add both user-srv and domain server present;
  ownership file maps domain server only.
- `test_add_backs_up_pre_existing_mcp_json` — seed, `add`, assert
  `~/.dotfiles-backup/.claude-mcp/<project>/.mcp.json.<ts>` exists.
- `test_add_writes_ownership_file`
- `test_two_domains_declare_same_server_ownership_records_both` —
  seed two domains with same server name; ownership map value is
  `[domain1, domain2]` in insertion order.
- `test_add_first_time_collision_user_wins` — user-owned server with
  the same name as a freshly-declared domain server; domain's config
  NOT written; WARN message captured.
- `test_add_repeat_collision_domain_wins` — seed ownership to include
  the name; `add` again rewrites the server; no WARN.

### Remove-side

- `test_remove_strips_only_domain_servers`
- `test_remove_deletes_mcp_json_when_last_domain_gone_and_no_user_servers`
- `test_remove_keeps_mcp_json_with_only_user_servers_remaining`
- `test_remove_removes_mcp_permissions_from_settings`
- `test_remove_drops_own_entries_from_enabled_mcpjson_servers`
- `test_remove_keeps_user_entries_in_enabled_mcpjson_servers`
- `test_remove_unsets_enabled_mcpjson_servers_when_empty`
- `test_remove_deletes_ownership_file_when_empty`

### Warnings

- `test_env_var_unset_emits_warning` — monkeypatch `os.environ` so
  `TEST_MCP_FOO` is unset; invoke `add`; assert warning text.
- `test_env_var_with_default_suppresses_warning` — fragment uses
  `${TEST_MCP_FOO:-bar}`; no warning.
- `test_requires_npm_missing_emits_warning` — seed
  `project_root/package.json` without `@test/mcptest`; warning fires.
- `test_requires_npm_present_silent` — seed with devDependency.
- `test_requires_npm_no_package_json_silent` — no package.json at all.

### Safety

- `test_symlinks_never_include_mcp_fragment_json` —
  check that after `add`, no symlink under `.claude/` points at
  `mcp.fragment.json` (skip-list assertion).

## E2E — `tests/e2e/test_mcp_cli.py`

- `test_add_then_remove_roundtrip_mcp`
  - Use `CliRunner` to:
    1. `init` a temp project
    2. `add @mcptest`
    3. Read `.mcp.json`, `settings.json`, `.claude/.ai-dotfiles-mcp-ownership.json`
       and assert:
       - `.mcp.json` has `mcpServers.mcptest-server`
       - `settings.json.permissions.allow` contains `mcp__mcptest-server__*`
       - `settings.json.enabledMcpjsonServers == ["mcptest-server"]`
       - ownership file maps `mcptest-server -> ["mcptest"]`
    4. `remove @mcptest`
    5. Assert `.mcp.json` is gone; ownership file is gone; permission
       and allowlist entries removed from `settings.json`.

## Definition of Done

1. `poetry run pytest -q` — entire suite green, including the new
   tests.
2. `poetry run mypy src/` — clean
3. `poetry run ruff check src/ tests/` — clean
4. `poetry run black --check src/ tests/` — clean
5. `poetry run pre-commit run --all-files` — clean
6. Coverage of the new code paths in `core/mcp_merge.py` and
   `core/mcp_ownership.py` should approach 100% (spot-check via
   `poetry run pytest --cov=src/ai_dotfiles/core/mcp_merge
   --cov=src/ai_dotfiles/core/mcp_ownership`).

Do NOT commit.
