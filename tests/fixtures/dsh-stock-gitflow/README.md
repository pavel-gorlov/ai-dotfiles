# Reviewed stock gitflow reproduction

Exact original catalog files observed for ai-ykwgd on 2026-10-06. The two
PreToolUse reminders are context-only; the script never vetoes a tool.
`gitflow.md` has no path activation and requires routing through the agent.
`python/settings.fragment.json` reproduces the other 31 allow-only warnings.
Other domain members are unnecessary to exercise this bounded hook fallback.

These originals intentionally retain Claude wording and model provenance;
tests prove native policy delivery, callable agent activation and inherited
session model. Changed contents must not silently update the compatibility
identity or relax negative tests.

These versioned originals anchor `_GITFLOW_SCRIPT_SHA`, `_GITFLOW_RULE_SHA` and
`_GITFLOW_AGENT_SHA` in [dsh_hooks.py](../../../src/ai_dotfiles/core/dsh_hooks.py).
They are a reviewed snapshot, not a canonical shipping catalog. CI copies these
committed fixtures into temporary catalogs; it never compares them against a
live `~/.ai-dotfiles` catalog.

For a deliberate maintainer re-review:

1. Compare the proposed catalog script, rule and agent with these originals.
   Verify a context-only script without vetoes, an unconditional routing rule,
   and an effective callable native agent inheriting the current session model.
2. Re-check the supported pinned DSH 0.2.0-rc.2 [official hook contract][dsh-hooks].
   The currently reviewed contract ignores `if` and PreToolUse `additionalContext`;
   verify its semantics before treating a new snapshot as compatible.
3. Only after deliberate review, update the fixture originals and all three pins
   together. Preserve changed-source refusal and the existing negative assertions,
   including effective policy/agent delivery and project-over-global precedence.
4. Run `tests/integration/test_dsh_gitflow.py`, positive/negative stock migration
   cases in `tests/e2e/test_dsh_migrate.py`, native RC2 policy/agent override
   acceptance in `tests/integration/test_dsh_runtime.py`, and the full project gate.
5. If emissions change for unchanged sources, revisit the appropriate generator
   version, including `DSH_HOOKS_GENERATOR_VERSION`, so existing outputs refresh.
   A review-documentation change alone does not change generated output.

[dsh-hooks]: https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md
