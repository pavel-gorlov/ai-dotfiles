---
id: ai-m4s7p
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_reconcile.py
- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/gitignore.py
- tests/integration/test_dsh_reconcile.py
- tests/integration/test_dsh_target.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 4
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-04T23:37:04+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T23:37:27+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T01:00:34+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Reconcile DSH drift retired sources and bounded prune

## Goal

Regenerate stale owned artefacts and retire deleted contributions while preserving mixed-target and user ownership.

Size driver: One reconciliation concern across five files, with a verified installer custody boundary, shared blocks and bounded prune.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 2, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_reconcile.py
- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/gitignore.py
- tests/integration/test_dsh_reconcile.py
- tests/integration/test_dsh_target.py

## Definition of done

- [x] Missing/source/generator/resource/contribution drift is reported consistently and regenerated in write mode.
- [x] Registry-versus-discovery retirement removes deleted local sources' owned outputs without touching user paths.
- [x] Check mode changes zero bytes and returns failure on drift; empty selected manifests clean up owned contributions.
- [x] Project prune consults the shared catalog/local union; global prune visits explicit owned roots/blocks and never walks home.
- [x] Managed link paths integrate with gitignore policy without ignoring an entire user AGENTS.md.
- [x] New tests cover check zero-writes, local preservation, single-target removal, bounded global prune and removed-source retirement.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.


## Execution notes

**backlog → to_do.** Prior migration ebe655bb verified against parent1976ead5:
exact10paths +2706/-72, frozen five source hashes and5/5 ticks; same commit
source/relocation/usage/journal and21-child cut. Pinned pre-commit/commit-msg/
whitespace exit0 with no mutations; clean index/tree, main baseline preserved.
Queue this sole four-file lifecycle owner for verified own-source shared refresh,
retirement, zero-write check and bounded prune. Guarded local-value activation
remains ai-wkpk8; never activate recorded aggregate or bypass local protection.

**to_do → wip.** tm ready and next select ai-m4s7p, parentai-f2pvj,
modewrite phase4. Sole current-model worker receives whole generated context,
approved epic and orchestration journal, exact four-file ownership. Six criteria
remain open pending concrete drift/retirement/native/regression/static evidence.

**Four-file probe → five-file custody boundary.** Worker original disposable
probe proves changed own local always_on rule is refused by preflight's fresh
registry union: Conflicting locally protected DSH block: local; registry bytes
unchanged, no source edits. Add dsh_install.py as the fifth owned boundary for
optional verified own-local-rule custody through preflight/apply. Default calls
retain current protection. Coordinator/consumer must prove exact prior source/
marker/inventory custody and preserve catalog/Codex protection in memory; no
registry deletion/temporary rewrite or user flag. Same lifecycle concern and
pre-decided2/10/11, not new scope. Writer finishes idle before whole-cut critic;
no continuation until BLOCKING0 and full regenerated context. Six ticks open.

**Five-file cut → verified continuation.** Fresh-context whole21-task critic
checks1–7: no findings, BLOCKING0; dsh_install overlap is ordered phases2→4.
Actual tm cut-check ai-f2pvj in worktree exits0, stdout '+ ai-f2pvj: cut-check
passed', stderr empty. Coordinator same check and validate49 exit0; original
disposable boundary script repeated exit0, stdout 'PROVED: Conflicting locally
protected DSH block: local', stderr empty. Source files unchanged before critic.
Resume same leaf/current-model owner with whole regenerated five-file context;
source_text SHA and previous local/source inventory/actual marker must agree,
Codex/catalog protection retained. Do not accept caller name sets as custody.
Six criteria remain unticked pending concrete lifecycle evidence.

**Repeat-migrate probe → historical custody correction.** Draft own22 gives
21pass/1fixture-helper ImportError, exit1; no acceptance. Concrete READYshared
→paths/MANUAL→repeat migrate retains rule_blocks but overwrites latest source
SHA/status/body. Reconcile refuses safely before writes, cannot retire the old
block. Worker freezes four drafted files. Continue same existing five-file
boundary: installer apply is also the migration producer and can retain exact
authoritative historical source/body/marker custody while keeping current source
classification, with validation/generator drift. No sixth file or new native
format/flag. If this real producer boundary cannot preserve proof, return exact
failure before ownership expansion. Fix owned fixture helper; all six ticks open.

**Generator regression → five-file test consolidation.** Historical custody
requires installer generator2. Worker unchanged target78 gives72pass/6fail;
coordinator independent same78 gate matches, exit1, only two old install1
assertions (119 dictionary,178–180 scalar) expanded across modes/scopes.
Replace planned separate prune context slot with existing test_dsh_target.py,
only these exact expected-version changes. All prune scenarios co-locate in
test_dsh_reconcile.py; preserve full tests/fixtures and existing discovery policy.
Current48 own gives47pass/1wrong independent-catalog fixture; use @bundle domain
member rather than manifest rule:local, which intentionally excludes that local
source. Draft prune278/SHA3ad33610 is preserved at temporary archive for same
owner consolidation/removal of its untracked original after freshcut0. Same
lifecycle concern, five final files/six criteria/21children/Q3 unchanged.
No source edits during fresh whole-cut review; all six criteria remain open.

**Test consolidation cut → verified continuation.** Fresh-context critic
checks all21 children/whole epic/contract, checks1–7 no findings, BLOCKING0.
Actual tm cut-check ai-f2pvj exits0, stdout '+ ai-f2pvj: cut-check passed',
stderr empty; coordinator structural check/validate49 also exit0. Writer was
frozen throughout. Resume existing5 final files, merge all prior untracked prune
tests intact into test_dsh_reconcile.py, remove only this owner's untracked
test_dsh_prune.py after archive/hash proof, update two old target expectations.
No other path or acceptance change.

**Root raw-CRLF probe → original-byte correction.** Disposable actual
multiline CRLF catalog skill installs then unchanged check falsely reports
source/generator contribution changed; shared always_on rule installs then
repeat check raises Conflicting DSH historical rule custody. Probe exit0 with
exact diagnostics. Expected source_text read_text normalized bytes; historical
shared body needs existing renderer/AGENTS normalization. Preserve original
raw text/SHA and native literal bodies, correct shared comparisons only and
add repeat/refresh/retirement cases in owned test file. Same5 concern, no new
scope; all six ticks remain open pending updated frozen gates.

**Fresh lifecycle probe → catalog-only selection boundary.** Worker reports
focused reconcile62/target78 gives140/140 and mypy87 exit0 after CRLF correction.
Concrete disposable fixture migrates registered skill, then adds unregistered
skill and catalog skill:sample: full opted-in reconciliation adopts the new
local output/registry key. That API is correct for full reconciliation but not
catalog-only install/add/remove. Same five-file owner assesses a narrow fresh
recorded-local selection before one composition; no inventory snapshot replay,
new user flag, sixth file or original/registry guard bypass. New sources must
remain unregistered while existing local contributors remain protected. CLI
owner is held until this concrete boundary is resolved and frozen gates pass.

**Producer selection → typed reconciliation hand-off.** Selection remains
ai-k1w43's bounded producer work. Its fresh selected DshLocalInputs also need a
public reconciliation input boundary; the current planner always recollects the
full local scope. Same owned dsh_reconcile.py may accept a verified typed fresh
input, preserving layout/catalog identity, original/registry guards and one
composition. No generic callback, snapshot or source-selection implementation
belongs here. Default full reconciliation stays unchanged. Repeat frozen gates
before acceptance after this narrow consumer join.


**Frozen implementation → verified acceptance.** Coordinator reviewed the whole
five-file implementation and the typed hand-off increment. Final owned diff
+1959/-11, SHA1a49ce5e; frozen five SHA match the worker report. Independent
focused reconcile/install gate169/169 exit0; worker same169/169 exit0. Whole
unchanged regression gate2222/2222 in127.53s exit0, stderr empty, including
required pinned native runtime. Initial sandbox-only loopback EPERM was followed
by the same full gate with isolated network permission; no skipped/altered test.
Root and worker mypy87, Ruff, pinned Black25.1 and whitespace all exit0.
Six criteria now verified: guarded drift/retirement and historical custody,
zero-write check, bounded prune/shared union and exact managed-link gitignore.
Typed local_inputs preserves full-reconcile default and original/registry guards;
registered-local selection belongs to ai-k1w43, guarded-value activation to
ai-wkpk8. No fresh local adoption is promised by catalog-only CLI yet.
Evidence: /private/tmp/dsh-m4s7p-typed-report.json and full stdout; source remains
frozen before acceptance/move/atomic commit.


**wip → done.** tm acceptance ai-m4s7p verifies6/6, exit0; tm move done
records the real transition and usage. Source/test changes, six ticks, original
backlog relocation, usage, both journals and the verified bounded catalog-only
cut will be committed together; next writer remains held until commit proof.
