Sync CLAUDE.md and CHANGELOG.md with recent changes.

## Instructions

You are updating the project documentation to reflect the current state of the codebase. Follow these steps.

### Step 1: Gather recent changes

Run these in parallel:
- `git log --oneline` from the last tagged release to HEAD — to see what changed
- Read the current `CLAUDE.md`
- Read the current `CHANGELOG.md`
- Read `pyproject.toml` for the current version

To find the last release tag:
```
git describe --tags --abbrev=0
```

Then get commits since that tag:
```
git log <tag>..HEAD --oneline
```

### Step 2: Scan the codebase for drift

Check if CLAUDE.md is out of date by looking at:
- **Commands section** — run `grep -r "add_argument\|add_parser" src/` to find all CLI subcommands and flags, compare with what CLAUDE.md lists
- **Architecture section** — check if any new modules were added under `src/`
- **Testing section** — check if new test files or markers exist in `tests/`
- **Repo Structure section** — check if any new top-level files or `.github/` files exist that aren't listed
- **Environment Variables** — check `config.py` for any new env vars

### Step 3: Propose updates

Show the user a summary of what's out of date:
- What's missing from CLAUDE.md
- What commits should be added to CHANGELOG.md (under an `[Unreleased]` section if not yet released)

Ask the user to confirm before making changes.

### Step 4: Update CLAUDE.md

Edit CLAUDE.md to reflect the current state. Keep the existing structure and style. Only add or update what's changed — don't rewrite sections that are already accurate.

### Step 5: Update CHANGELOG.md

If there are unreleased changes since the last tag, add them under an `[Unreleased]` section at the top of CHANGELOG.md. Group changes by type:
- **Added** — new features
- **Changed** — changes to existing functionality
- **Fixed** — bug fixes
- **Removed** — removed features

If there are no unreleased changes, skip this step.

### Step 6: Commit

```
git add CLAUDE.md CHANGELOG.md
git commit -m "Sync docs with recent changes"
```

Do NOT push — let the user decide when to push.
