# Gitflow rules

Ambient policy for git work. Loaded every session by Claude Code. Procedural *how* lives in the `@gitflow` skills the agent loads on demand.

## Core workflow — trunk stays linear, squash-merge at landing

`main` stays linear: every PR lands via squash-merge, so trunk history is exactly one commit per merged PR regardless of what happened on the feature branch. An epic branch carries one commit per subtask; squash-merge collapses all of them into that one trunk commit — a squashed epic PR is one commit on `main`, same as any other PR. A feature branch is not required to stay linear internally — a sync merge commit on the branch is fine (see below) because squashing at landing normalizes it away. Sources: trunkbaseddevelopment.com/short-lived-feature-branches, docs.github.com PR-merge-methods, docs.gitlab.com merge-methods.

The default sync-with-trunk loop on a small feature branch (see thresholds below):

```bash
git fetch origin
git rebase origin/main
# resolve conflicts, run the project's quality gate
git push                    # fast-forward — no force needed
```

Never `git pull` on a long-lived branch — it creates merge commits. Use `git pull --rebase` or `fetch + rebase` explicitly.

## Event-driven sync, not cadence

Sync a feature branch with trunk only when one of these fires — not on a schedule:

1. a conflict exists,
2. a shared contract changed,
3. CI requires an updated base,
4. the branch is about to land and there is no merge queue,
5. the user explicitly asks for a sync.

Cadence-based resyncing ("rebase early and often") is not required under this policy.

## Pre-integration triage

Before picking a sync/integration mechanism, probe for conflicts against trunk. The probe command (`git merge-tree`, git ≥2.40) and its output-reading playbook live in `skills/rebase/` — run it first, then choose plain rebase vs. squash/replay vs. merge-once below.

**A clean probe means no sync.** If the final states merge cleanly and none of the event triggers above fired, leave the branch alone — trunk moving is not a reason to rewrite a feature branch.

## Decision tree — small vs. large branches

Initial calibration, not a runtime config system — one canonical location, this section:

- **Small** (all hold): ≤5 feature commits, ≤5 overlapping files, ≤1000 changed LOC. A conflicted small branch still uses plain rebase.
- **Large** (any holds): >15 feature commits, >10 overlapping files, >3000 changed LOC, or generated/binary/migration conflicts present. A conflicted large branch avoids commit-by-commit replay by default — use one of the two mechanisms below instead.
- Semantic overlap always overrides the numeric thresholds, in either direction.

Revisit these numbers after the first 3 large-branch integrations land under this policy, or immediately if any one of them is visibly misclassified by the numbers — whichever comes first.

## Large-branch integration: disposable vs. published

**Disposable / unreviewed branch** — integrate via final-state squash/replay from fresh trunk; keep the original branch as a recovery point until the integration validates:

```bash
git switch -c integrate/<task> <trunk>
git merge --squash feature/<task>
```

**Published / reviewed / shared branch** — merge trunk into the feature branch once, preserving SHAs and review context:

```bash
git merge <trunk>
```

Run this once per sync event, not repeatedly. The resulting merge commit on the feature branch is allowed — trunk landing is squashed, so it never reaches `main`.

## Generated, binary, and migration artefacts

Handle these (API clients, lockfiles, Playwright baselines, Alembic graphs, etc.) once, after semantic integration completes — never per replayed commit.

## Semantic-conflict validation

Stays required independently of textual merge-cleanliness: re-read shared-contract assumptions and run targeted tests even when git reports no conflicts.

## Push hierarchy

1. **Fast-forward push — the default.** If your local commits sit cleanly on top of `origin/<branch>`, plain `git push` works. No history rewrite, no force.
2. **`--force-with-lease`** — only when a rebase rewrote *your* published branch. Prefer the explicit-SHA form `--force-with-lease=<branch>:<expected-sha>` when the fetch may be stale. Refuses if the remote moved under you.
3. **Plain `--force`** — forbidden. Silently stomps concurrent pushes.

## Work through the agent

For any git/gh mutation — `commit`, `rebase`, `push`, `merge`, `cherry-pick`, `revert`, `reset --hard`, `worktree`, `gh pr create/edit/merge` — invoke `git-workflow-assistant`. A PreToolUse hook nudges toward it; follow the nudge. Direct mutation is the exception, not the default.

## Skills in the domain

- `skills/commit/` — Conventional Commits message authoring.
- `skills/rebase/` — rebase playbook (autosquash, `--onto`, `--update-refs`, `rerere`, conflict resolution, cherry-pick replay), plus the pre-integration triage probe.
- `skills/git-worktree/` — parallel workspaces, subagent isolation.
- `skills/revert-merged-pr/` — undoing a merged PR (`-m 1`, revert-of-revert trap).
- `skills/pr-authoring/` — opening a PR (pre-flight, title, body, draft/ready, reviewers).
- `skills/pr-reflection/` — post-merge lessons-learned doc.

## Non-negotiable policy

> One PR per epic from one branch, with one commit per subtask. A PR is cut only right before a live step that needs merged code — a deploy, a cutover, or a rehearsal of installed skills or CLIs — and the work so far merges there; the rest continues on the next branch (`epic/<epic-id>`, then `epic/<epic-id>-2`, …). Phases are milestones inside a PR.

- **`main` is production.** Never commit directly unless the repo's precedent is flat-on-main (verify via `git log`).
- **One PR = one epic (or one cut before a live step), or one standalone task** — one commit per subtask on epic branches, with a Conventional Commits-style title and a *what / why / how-to-verify* body.
- **Atomic commits** — one logical change each; body explains *why*.
- **Quality gate green before push** — whatever the project defines (pre-commit hooks → task runner → CI config → README).
- **No secrets in the diff** — ever.
- **An open PR stays truthful.** Any functional change pushed to a branch with an open PR updates, in the same push, the PR description, the affected documentation and the linked task's text. Procedure: `skills/pr-authoring/` → *Keep an open PR in sync with its branch*. In a `@taskmanager` project in server mode, the linked task's text is updated on the server — through the routed `tm` command, or `tm push` after a hand edit to the mirror file — rather than committed with the push.
- **Retire the branch after its PR squash-merges.** Follow-up work starts a fresh branch from updated trunk rather than continuing commits on the squash-merged branch — continuing there causes confusing divergence. Sources: docs.github.com PR-merge-methods, docs.gitlab.com merge-methods, support.atlassian.com Bitbucket squash-commit diff note.
- **Squash commits on trunk still carry Task-Id linkage** — Conventional Commits scope (`feat(<id>): ...`) or `Task-Id: <id>` trailer, per `taskmanager.md`. Squashing doesn't excuse dropping the task reference. This footer is unaffected by server mode — it names the task in commit-message text, not the mirror file that stops being git-tracked there.

## Cross-cutting

Git-specific habits the gitflow agent owns: split mixed-intent commits before push, narrate long rebases, never bypass hooks (`--no-verify`, `--no-gpg-sign`). General blast-radius / destructive-action policy lives in `engineering-principles` and the Claude Code system prompt — don't restate here.
