---
name: push-main
description: This skill should be used when the user asks to "push to main and clean worktree", "push to main", "推送到 main 并清理", "push commit to main then clean worktree", "merge and clean", or wants to push/merge the current branch into remote main and clean up.
---

# Push to Main & Clean Up

Push or merge the current branch into remote `main`, then clean up the local branch or worktree.

## Prerequisites

- All changes intended for main have been committed.

## Workflow

### Step 1: Gather Context

Run in parallel:

```bash
git branch --show-current
git rev-parse --abbrev-ref HEAD
gh pr list --head <current-branch> --state open --json number,url --limit 1
```

Determine:
- **current branch**: the branch name
- **is worktree**: whether the session is inside a worktree (branch name starts with `worktree-` or differs from `main`)
- **has open PR**: whether a PR exists for this branch

### Step 2: Merge or Push

**If an open PR exists** for the current branch:
- Merge the PR via `gh pr merge <number> --merge --delete-branch`
- This respects branch protection rules and CI checks.

**If no open PR exists:**
- Push directly: `git push origin <current-branch>:main`
- If the push is rejected (non-fast-forward or branch protection), stop and report the error. Do NOT force-push.

### Step 3: Clean Up

**If in a worktree session** (created by `EnterWorktree`):
- Invoke `ExitWorktree(action="remove", discard_changes=true)`
- Safe because the commit has already been pushed/merged to remote main.
- After exiting, the session returns to the main repository (typically on the default branch).

**If on a regular local branch** (not a worktree):
- Switch back to main: `git checkout main`
- Delete the local branch: `git branch -D <branch-name>`

In both cases, sync the local default branch in Step 4 below.

### Step 4: Sync Local Default Branch

After cleanup the session is on the local default branch (`main` or `master`), which now lags remote by exactly the commit just pushed/merged. Pull it down with rebase, matching the `pull-rebase` skill's strategy:

```bash
git pull --rebase
```

- Since the local default branch has no commits ahead of remote, this is a clean fast-forward — no conflicts expected.
- If `git pull --rebase` fails (e.g. unexpected divergence, no upstream), report it but do NOT force anything; the push/merge already succeeded, so this is a non-fatal follow-up.

### Step 5: Report Result

Confirm:
- Whether the action was a **direct push** or **PR merge**
- The commit hash
- That the branch/worktree was cleaned up
- That the local default branch was synced (or note if the sync was skipped/failed)

## Error Handling

- If push fails due to branch protection or non-fast-forward, suggest creating a PR instead.
- If PR merge fails (CI not passed, review required), report the blocker.
- If `ExitWorktree` fails, suggest manual cleanup with `git worktree remove`.
- If the Step 4 `git pull --rebase` fails, report it as a non-fatal follow-up — the push/merge already succeeded; do NOT force-push or reset.
