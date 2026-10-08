---
id: ai-xj3q9
kind: task
status: done
created_at: '2026-10-05T23:58:12+00:00'
parent: ai-47xpm
dependencies: []
context_files:
- tests/unit/test_dsh_paths.py
- tests/unit/test_dsh_targets.py
- tests/unit/test_dsh_render.py
- tests/unit/test_shared_instructions.py
- tests/unit/test_elements.py
- tests/unit/test_targets.py
status_history:
- at: '2026-10-05T23:58:12+00:00'
  status: to_do
- at: '2026-10-06T00:00:21+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-06T00:31:49+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Relocate DSH filesystem tests after review

## Intake

Owner request: `$cc-review --fix` on the existing ready PR #22.

## Context

PR #22 contains the completed DSH epic and passed GitHub CI at
`21e62d4a603a8d5aab0c53ac62668af53f9a8078`: 2426 tests, native 15/15,
coverage 92.04%. Four independent review passes found one instruction-compliance
candidate. Fresh adversarial validation confirmed it as P2: the root instruction
defines `tests/unit` as `fast, no I/O, no subprocess` and puts filesystem and
symlink tests in `tests/integration`.

Validation identifies 84 new filesystem-backed test definitions in six modules
and 18 pure definitions to keep in unit. Existing filesystem tests in the mixed
`test_elements.py` are historical and outside this correction. A plain follow-up
task is sufficient for this mechanical correction; it belongs to the same epic
and existing PR explicitly selected by `--fix`, without changing the approved
22-child implementation cut or closed task history.

Frozen review evidence is under `/private/tmp/dsh-cc-review-22/`:
`inputs.json`, `pr-metadata.json`, `pass1.json` through `pass4.json`, and
`validation-unit-io.json`. The last file contains exact definitions, changed-line
provenance, disproof attempts and pure-case exclusions. The primary anchor is
`test_dsh_paths.py:81-83` (`mkdir` and `symlink_to`).

## What to do

1. Move the confirmed new filesystem-backed cases and required I/O builders to
   corresponding modules under `tests/integration`, with the integration marker.
   Pure planning cases may stay in unit if their filesystem boundary is fully
   mocked; document every such disposition. Preserve all existing assertions,
   parameterizations and coverage, and retain the 18 identified pure unit cases.
2. Only the six `tests/unit` modules listed in `context_files` and corresponding
   integration modules with the same basenames may change. Preserve old mixed
   module tests and helpers unless removing an import made unused by relocation.
   Do not change production code, rules, dependencies, old done tasks or homes.
3. Record before/after test-definition and collected-instance mappings. Compare
   moved test bodies and parameterizations; explain only necessary import/helper
   relocation or pure filesystem-boundary mocking. Verify the collected total
   remains 2426 with no lost, duplicated or newly skipped cases.
4. Run the focused affected modules and full pytest with coverage and required
   native tests, then mypy, Ruff, Black, all six full pre-commit checks and
   whitespace. Use the existing isolated Poetry/pre-commit caches and official
   DSH 0.2.0-rc.2 fixture; `_AI_DOTFILES_TEST_DSH_RUNTIME` points to
   `/private/tmp/dsh-bridge-native-rc2`. Never skip required native tests.
5. Return a frozen report with exact edits, per-definition disposition,
   actual commands/cwd/environment/exits and complete stdout/stderr log hashes,
   collection/JUnit/coverage/native proof and preserved production/main evidence.
   The root verifies it, closes this task and records one atomic task-linked
   commit through the Git specialist, updates PR metadata and waits for CI.

## Acceptance criteria

- [x] All 84 confirmed new filesystem-backed definitions have an evidenced integration or fully mocked-unit disposition; the 18 identified pure cases remain unit.
- [x] Production source, dependencies, rules, old mixed-module tests, closed task history and the owner's original main bytes/index/HEAD/status are preserved.
- [x] Before/after test definitions, bodies and parameterizations are accounted for; collection remains exactly 2426 without lost or duplicate cases.
- [x] Focused tests and full pytest pass with coverage at least 80%, zero skips and all 15 required native runtime cases.
- [x] Mypy, Ruff, Black, all six full pre-commit checks and whitespace pass on the final frozen correction.
- [x] Complete worker evidence is independently verified and no process or source write remains after the final gates.

## Anti-patterns

- Replacing real integration coverage with weak mocks just to keep test paths.
- Moving pre-existing unrelated unit filesystem tests or pure unit cases.
- Changing DSH behavior or weakening assertions, markers, permission tests or CI.
- Editing done history, publishing review comments, or performing Git mutations
  in the implementation worker. The owner did not request `--comment`.

## Execution notes

- **Review → correction queued.** Four fresh-context review passes completed on
  the immutable PR head; one P2 instruction violation survived adversarial
  validation. The owner requested fixing it in the same PR. No new feature or
  user-visible decision is introduced.

- **Correction accepted.** All 84 confirmed definitions moved to the six
  corresponding integration modules with `pytest.mark.integration`; their full
  AST, arguments and decorators are identical. The 18 pure definitions remain
  unit. Only three pure CWD cases replace `monkeypatch.chdir` with a stub of
  `paths.current_dir`, retaining their assertions and parameters. Existing mixed
  module tests and helpers are unchanged. Independent AST accounting covers all
  1458 test definitions; before/after collection has exactly 2426 unique cases,
  including the same 254 moved instances and 15 unchanged native cases.
- **Final gates passed.** Focused 337/337 and full 2426/2426, zero skipped,
  failed or errored; native 15/15; coverage 92.04% (9737/10579 lines). Mypy,
  Ruff, Black, whitespace and all six hooks pass both for the explicit 12-path
  allowlist and for `pre-commit run --all-files`. Formatting preceded the final
  tests; no source changed after the gates. The scratch evidence collector's
  directory-filter error is retained separately and corrected only in temporary
  tooling; it is not a product or gate failure.
- **Root evidence verified.** Whole 3516-line diff read, all 44 actual command
  records and complete stdout/stderr bytes and SHA verified. Frozen report:
  `/private/tmp/dsh-cc-review-22/fix-report.json`, SHA
  `08354b0a6442635435e4365d764ef6c66464268f6a01940873d419396cb857d4`.
  Independent proof and review: `fix-root-independent.json` and
  `fix-root-reviewed.json` in the same directory. All 337 nonowned tracked
  worktree files and original main's 260 tracked/26 untracked files, modes,
  index, HEAD and status are preserved. Worker ended frozen and uncommitted;
  no process or source writer remains. Publication updates the same PR #22
  through one atomic task-linked commit; remote CI follows that commit.
