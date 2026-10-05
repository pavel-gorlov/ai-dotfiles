---
id: ai-fcbgs
kind: subtask
status: done
created_at: '2026-10-05T07:12:10+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/core/codex_rules.py
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md
executor_agent: claude
size: S
mode: write
phase: 8
status_history:
- at: '2026-10-05T07:12:10+00:00'
  status: backlog
- at: '2026-10-05T07:22:15+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T07:23:23+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T07:52:40+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
dependencies:
- ai-7xrwf
---

# Align final help and formatter gates

## Goal

Resolve the two demonstrated final acceptance blockers without changing command behavior or tooling.

Size driver: Two finite help/format edits found by the same final audit; no unknowns or implementation behavior changes.

## Scope and ownership

Continue the approved epic's final documentation and quality gates (Pre-decided
decisions 1, 2, 15). The immutable ai-pwjnx audit passed2426 tests/native15,
coverage92.04%, then stopped at pre-commit and reported two material blockers.
Its report is /private/tmp/dsh-pwjnx-report.json.

Write ownership is exactly src/ai_dotfiles/commands/add.py (only the add command
help/docstring) and src/ai_dotfiles/core/codex_rules.py (only the formatter-added
trailing comma in _expected_text). The original DSH lifecycle concern was
ai-k1w43; its done history stays immutable. The baseline Codex change was emitted
automatically by pre-commit Black25.1, not implemented by the read-only auditor.
Validate and adopt that exact existing comma; do not restore/reformat other code.

The builtin skill and DSH guide are read-only references, already updated in
this PR to describe selected targets. No flag, default, routing, API, policy,
test, profile, tool version or template behavior changes belong here.
ai-pwjnx remains idle wip at the later barrier until this writer is accepted
and atomically committed. It then owns a fresh whole-cut acceptance pass.

## Context files

- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/core/codex_rules.py
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md

## Definition of done

- [x] Actual add --help describes installation for selected targets, preserving all options; isolated DSH-only project/global and default-Claude add outcomes agree with that wording.
- [x] The Codex edit is exactly the pre-commit trailing comma, with unchanged AST; Poetry Black24.10 and pinned pre-commit Black25.1 accept both owned files without mutation.
- [x] The complete source diff changes only the two permitted lines; add behavior AST except its docstring is unchanged and the shipped builtin skill/DSH guide already agree in this same PR.
- [x] Existing relevant add/DSH/Codex tests, focused Ruff/mypy, pinned checks on owned files and whitespace checks pass with actual commands/outputs; final whole-cut gates remain ai-pwjnx's responsibility.

## Notes

No new tests are needed for these reversible help/format edits. Use existing
tests plus real isolated CLI outcomes and semantic comparison. Preserve others'
changes; do not commit, tick acceptance or mutate task metadata. Return a frozen
two-file diff, source SHA, actual argv/cwd/stdout/stderr/exit and all processes ended.

## Execution notes

**backlog → to_do.** Fresh-context critic read all24 files/4556 lines and all22
children, checks1–7 PASS/BLOCKING0/advisory0; its actual cut-check0/stdout
"+ ai-f2pvj: cut-check passed"/stderr empty. Root cut-check0/validate50/33legacy/
whitespace0. Queue only this S corrective writer; ai-pwjnx remains idle wip9.
Four concrete ticks remain open. Current-model worker receives whole context
and exacttwo-file ownership; source changes must be accepted/committed before
the final verifier resumes. Evidence /private/tmp/dsh-final-corrective-cut-critic-report.json.

**to_do → wip.** Actual ready/next select this sole writeS phase8 member;
claim before complete tm context + whole approved epic/current orchestrator
dispatch. No other worker or Git executor active. The original Codex comma
remains exactly the observed automatic pre-commit mutation. No tracker/Git/ticks
belong to the worker; final six verifier criteria remain open until fresh audit.

**wip → done.** Root reviewed the entire two-line source diff and all27 actual
command records/stdout/stderr/exits; stream bytes and SHA match disk, all processes
ended. Report /private/tmp/dsh-fcbgs-report.json SHA
6eead59ca406d40b7950a0db9a5ab9b6e8b5ec9dff05cd642c71844bba853c48;
root review /private/tmp/dsh-fcbgs-root-reviewed.json. Existing120 tests passed
with0skip; mypy/Ruff/both Black checks/six precommit hooks/whitespace exited0.
The pinned configured Black25.1.0 source is proven by clean official checkout
8a737e727ac5ab2f1d4cf5876720ed276dc8dc4b/FETCH_HEAD/cache DB and all25 installed
source hashes; its actual shallow-SCM binary reports0.1.dev1+g8a737e727, while
Poetry Black reports24.10.0. No pins/cache/tooling changes or waivers. Two failed
scratch report/provenance assumptions were corrected only in /private/tmp and
remain in evidence. Root independently verified whole AST invariance except
add docstring, exact owned SHA and actual selected-target add help/options. Three
isolated real CLI outcomes agree with existing same-PR references. All339
nonowned paths/index/HEAD/main state stayed unchanged. Four criteria now checked;
acceptance and normal transition precede the single atomic corrective commit.
ai-pwjnx remains idle wip9/all6 open until that commit is independently verified.
