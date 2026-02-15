Clean up stale branches after merged PRs.

## Instructions

You are cleaning up local and remote branches that are no longer needed. Follow these steps in order.

### Step 1: List all branches

Run `git branch -a` to see all local and remote branches.

Identify branches that are NOT `master` or `remotes/origin/master` or `remotes/origin/HEAD`.

If there are no extra branches, tell the user everything is clean and stop.

### Step 2: Show the user what will be deleted

List the branches grouped by:
- **Local branches** to delete
- **Remote branches** to delete
- **Stale remote refs** to prune

Ask the user to confirm before proceeding.

### Step 3: Delete local branches

Delete all local branches except `master`:

```
git branch -d <branch1> <branch2> ...
```

If `-d` fails (unmerged branch), report it and ask the user if they want to force-delete with `-D`.

### Step 4: Delete remote branches

For each remote branch (except `master`), delete it:

```
git push origin --delete <branch1> <branch2> ...
```

If a remote branch no longer exists (already deleted on GitHub), that's fine — proceed to pruning.

### Step 5: Prune stale remote refs

```
git remote prune origin
```

### Step 6: Verify

Run `git branch -a` and confirm only `master` and `remotes/origin/master` remain.

Report what was cleaned up.
