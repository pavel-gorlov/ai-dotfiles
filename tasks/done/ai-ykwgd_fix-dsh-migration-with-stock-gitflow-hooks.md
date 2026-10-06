---
id: ai-ykwgd
kind: task
status: done
created_at: '2026-10-06T20:07:23+00:00'
parent: null
dependencies: []
status_history:
- at: '2026-10-06T20:07:23+00:00'
  status: backlog
- at: '2026-10-06T20:17:30+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-06T20:17:53+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-06T20:39:44+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Fix DSH migration with stock gitflow hooks

## Intake

> $intake нужен фикс

## Context

Follows up `ai-4m4hj`, `ai-nzmc8`, `ai-wkpk8` and `ai-gbrqm`, delivered
in PR #22 and release v0.4.0. The older working copy still has pre-merge
tracker statuses; do not reopen or rewrite the shipped tasks.

The real project selects Claude, Codex and DSH, with `@gitflow` and `@python`.
`ai-dotfiles migrate --to dsh --dry-run` exits successfully, labels the local
configuration `MECHANICAL`, reports 55 nonblocking `ALLOW_UNMAPPED` warnings
and two `HOOK_UNMAPPED` diagnostics, then recommends applying the migration.
The actual `ai-dotfiles migrate --to dsh` exits 1 before writing because both
stock `@gitflow` PreToolUse handlers have an unsupported `if` option:
`Bash(git *)` and `Bash(gh *)`.

Both handlers call `$CLAUDE_PROJECT_DIR/.claude/hooks/route-to-agent.sh`.
The stock script filters mutating git/gh commands itself and returns only a
PreToolUse `additionalContext` reminder to use `git-workflow-assistant`;
it never vetoes commands. The existing always-on `gitflow.md` rule already
requires this delegation. Removing `if` alone would leave an ineffective
reminder: DSH's Claude hook bridge ignores PreToolUse `additionalContext`.

Size: **M** — one PR covering a narrowly verified stock-hook adaptation,
effective rule/agent delivery, migration readiness output and native regression.

Authoritative context:

- [Current DSH hook contract](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md), checked 2026-10-06: handler `if` is not honored and PreToolUse context is ignored.
- [Released DSH guide](https://github.com/pavel-gorlov/ai-dotfiles/blob/v0.4.0/docs/dsh-target.md); supported native acceptance baseline is DSH 0.2.0-rc.2.
- `core/dsh_hooks.py`, `core/dsh_migrate.py`, `commands/migrate.py`,
  `tests/unit/test_dsh_hooks.py`, `tests/e2e/test_dsh_migrate.py` and
  `tests/integration/test_dsh_runtime.py` in the released source tree.
- Catalog sources: `gitflow/settings.fragment.json`,
  `gitflow/hooks/route-to-agent.sh`, `gitflow/rules/gitflow.md` and
  `gitflow/agents/git-workflow-assistant.md`.

## What to do

1. Reproduce the reported project configuration in an isolated fixture using
   the shipped v0.4.0 behavior and actual stock catalog sources. Start any
   implementation branch from current merged trunk, preserving the owner's
   dirty working copy and the earlier epic/release worktrees.
2. Add explicit DSH handling for this stock, context-only `@gitflow` reminder
   when its catalog provenance and supported contents are verified. Retain
   routing through the existing always-on policy and callable native agent.
   Verify effective delivery before retiring the redundant DSH hook entries;
   a domain name, filename or matching command string alone is insufficient.
3. Report the adaptation with its origin and the actual supported behavior:
   routing policy remains available, while the additional per-command hook
   nudge is absent. Do not label this as faithful `if` translation or native
   PreToolUse context support. If stock identity, rule delivery or agent
   availability cannot be proved, retain an actionable blocking diagnostic.
4. Use the same guarded handling throughout project migration and applicable
   project/global catalog activation and reconciliation. Preserve ownership,
   drift detection, repeat-run idempotence and safe retirement of generated
   artifacts. Project migration must not rewrite user global profiles.
5. Make dry-run distinguish blocking diagnostics from nonblocking limitations
   and state whether activation is ready. A blocked preview must not conclude
   with an unqualified recommendation to apply; keep dry-run write-free.
6. Add focused behavioral and pinned native-runtime regression coverage, then
   update `docs/dsh-target.md` and the shipped
   `scaffold/templates/builtin_ai_dotfiles_skill.md` in the same PR.

## Acceptance criteria

- [x] An isolated reproduction of the real `@gitflow` + `@python` configuration successfully migrates to DSH; the two verified stock reminders do not block activation and the adaptation is explicitly reported.
- [x] The stock gitflow routing rule and callable `git-workflow-assistant` are proved present in the effective native DSH configuration/context before relying on them; native agents continue to inherit the current session model.
- [x] A changed script, unverified source, missing routing rule or unavailable agent cannot enter this compatibility path; no arbitrary custom handler is silently dropped or widened.
- [x] Unrelated unsupported `if` handlers and other required hook semantics remain blockers; supported command hooks retain their ordering, conditions and resource provenance.
- [x] Existing allow grants remain nonblocking `ALLOW_UNMAPPED` diagnostics; deny/ask restrictions, native presets and sandbox decisions are neither broadened nor disabled.
- [x] A blocked dry-run clearly distinguishes blockers from limitations and reports activation as blocked without recommending unconditional apply; both dry-run and a refused apply preserve all pre-existing bytes and ownership records.
- [x] Applicable project/global catalog lifecycle and migrated-project paths share the guarded behavior; install/reconcile repeat runs do not duplicate policy or hook output, and drift/removal respect existing ownership.
- [x] Focused CLI/filesystem tests cover the reported success case and the negative cases above, with fixtures confined to temporary roots. Pinned stock DSH acceptance proves actual policy and agent activation rather than only successful JSON parsing.
- [x] Existing Claude and Codex hook behavior, user-owned global/project configuration and unrelated local elements remain unchanged; documentation and the builtin CLI skill describe the supported fallback and dry-run readiness accurately.

## Out of scope

Exact event-time context restoration through a new native interceptor/plugin;
general translation of arbitrary Claude `if` expressions or script semantics;
new flags, compatibility registries or configurable fallback modes; upstream
SDK upgrades; changes to permission grants; automatic edits to the owner's
live catalog, hook scripts, manifests, profiles or provider/model selection.

## Pre-decided decisions

Execution follows the existing task scope selected by the owner through
`$orchestrate ai-ykwgd`: use the already required always-on gitflow policy for
the verified stock context-only reminder, explicitly report the missing
per-command nudge, and retain all custom-hook and permission blockers.
Do not introduce a new native interceptor, flag or configuration mode.
Use the current session model for dispatched workers and native agents.

## Execution notes

**backlog → to_do.** 2026-10-06: selected single-item execution, parentless and
without dependencies. Branch `fix/ai-ykwgd-dsh-gitflow` in
`/private/tmp/ai-dotfiles-ai-ykwgd` starts at fresh `origin/main`
`a2d741bdc0068d9f2a8daf83c1634d2c7589cdb8`. Installed v0.4.0 bootstrap and
status exited 0 with 28 healthy links against a temporary exact stock catalog
copy; live catalog/configuration and earlier worktrees are preserved.
Local gate, all in this worktree: `poetry run ruff check src/ tests/`,
`poetry run black --check src/ tests/`, `poetry run mypy src/`,
`poetry run pytest --cov --cov-report=xml` (coverage >=80%, native DSH required),
and `poetry run pre-commit run --all-files`. Goal line emitted in the transcript;
no goal API or session configuration changed.

Pre-existing, do not fix in this branch: the shipped DSH epic/orchestrator have
stale tracker states in older checkouts; no prior feature worker remains active.
Bootstrap's optional runtime provisioning reported commitizen absent in an
empty offline uv cache; development dependencies are handled by Poetry, not
live catalog/tool installation. The earlier unmerged test-lane cleanup from
`epic/ai-47xpm` is outside this task and must not be replayed.

**to_do → wip.** 2026-10-06: `tm ready --json` selected `ai-ykwgd` as the sole
eligible write assignment. Coordinator owns this task's journal and acceptance;
one worker owns bounded DSH hook/migration/lifecycle changes, relevant behavioral
tests, `docs/dsh-target.md` and the builtin CLI skill. No substantive parallel
writer or active ownership conflict exists. Complete `tm context` is supplied
as `/private/tmp/dsh-ai-ykwgd-evidence/context.md`; worker changes stay
uncommitted until coordinator acceptance and the Git executor's transaction.

In progress: the worker identified the three producer paths and has initial
changes in `core/dsh_hooks.py`, `core/dsh_migrate.py`, `core/dsh_reconcile.py`,
`core/dsh_launch.py`, `commands/migrate.py` and `tests/e2e/test_dsh_migrate.py`.
Source-level READY labels alone are insufficient: changed routing text and
effective native agent/policy overrides must remain guarded. Native delivery,
negative cases, documentation and the full frozen-diff gate are still pending;
all nine acceptance criteria remain unchecked.

Baseline reproduced with the installed Homebrew v0.4.0 CLI in a temporary
fixture: dry-run exited 0 with 55 `ALLOW_UNMAPPED` and two `HOOK_UNMAPPED`,
apply exited 1. Logs: `/private/tmp/dsh-ai-ykwgd-evidence/worker/reproduction/`.
The initial focused check had 270 passed and two failures exposing lost
hook/config diagnostics in lifecycle reports. The worker has wired diagnostic
delivery and is rerunning the check; the failed attempt is retained. Required
RC2 coverage now includes a real callable child with routing policy in the
parent's request and refusals for effective agent/policy removal. These checks
still require successful recorded results before acceptance.

The substantive diff is now frozen at 16 owned paths in
`/private/tmp/dsh-ai-ykwgd-evidence/worker/frozen-sources.json`, manifest SHA256
`f771b316e09f15a74b95133d328fbf569e2bb24f278ca66fb6e96498910121c3`.
The final focused check passed 275 tests; the three new stock RC2 cases passed.
Initial native assertion failures are retained in worker logs; they were
diagnostic-code expectation mismatches, corrected without dropping actual
delivery/refusal assertions. Full frozen-diff Ruff, Black and mypy have exited
0; full coverage pytest is running with scoped host execution for required
loopback/native scenarios. An independent read-only acceptance review is active.
All nine criteria remain unchecked until the full required gate and review end.

Coordinator independently reran `poetry run pytest
tests/integration/test_dsh_gitflow.py tests/e2e/test_dsh_migrate.py -q` with
`VIRTUAL_ENV=/private/tmp/ai-dotfiles-ai-47xpm/.venv` and
`PYTHONPATH=/private/tmp/ai-dotfiles-ai-ykwgd/src`: exit 0, 69 passed in 12.67s.
Verified imported package path in this worktree and Python 3.12.13. Evidence:
`/private/tmp/dsh-ai-ykwgd-evidence/independent-focused-proof.json`.
Pre-existing, do not fix in this branch: the full suite's vendor meta-search
E2E performs a real public `printing-press-library.git` clone into its pytest
temporary vendor cache; keep the established full gate without lane cleanup,
registry stubbing or skips.

**wip → done.** 2026-10-06: coordinator verified the actual diff, source
fingerprints and recorded command output; independent read-only review returned
PASS with all nine criteria supported. `tm acceptance ai-ykwgd` exited 0 with
9/9 checked and `tm move ai-ykwgd done` exited 0 without force. The frozen
16-file implementation contains the exact-source stock fallback, all three
producer callers, generator version 2, readiness reporting, isolated fixtures,
behavioral/native tests, guide and builtin skill; +1062/-10 substantive lines.
Full worktree-local Python 3.14.8 gate: 2449 passed in 252.83s, 18 required
published RC2 cases, zero skips/xfail, coverage 92.09%; Ruff, Black (183 files),
mypy (87 modules), all six pre-commit hooks and supplemental new-file hooks
exited 0. Coordinator's separate 69 cases passed on Python 3.12.13. All check
attempts are retained, including initial focused/native assertion failures.
Evidence: `worker/acceptance-evidence.json`, `review-report.json` and
`independent-focused-proof.json` under `/private/tmp/dsh-ai-ykwgd-evidence/`.
Source fingerprint remains `f771b316e09f15a74b95133d328fbf569e2bb24f278ca66fb6e96498910121c3`;
no worker processes or source changes remain. The Git executor must include
work, acceptance and this closure journal in one commit and verify that
transaction before completion is reported. Own-branch PR follows the accepted
orchestration flow; merge/release/install are outside this run.
