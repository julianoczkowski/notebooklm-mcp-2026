Release a new version of notebooklm-mcp-2026 to PyPI.

## Instructions

You are automating the release process for the `notebooklm-mcp-2026` Python package. Follow these steps in order. If any step fails, stop immediately and report the error — do NOT proceed to later steps.

### Step 1: Pre-flight checks

Run these in parallel:
- `ruff check src/ tests/` — lint must pass
- `pytest -v --tb=short` — all tests must pass
- `git status` — working tree must be clean (no uncommitted changes). If there are uncommitted changes, stop and ask the user to commit or stash them first.
- `gh auth status` — GitHub CLI must be authenticated

If any check fails, stop and report the issue.

### Step 2: Determine version

Read the current version from `pyproject.toml` (the `version` field under `[project]`).

Ask the user what kind of bump they want:
- **patch** (e.g. 0.1.2 → 0.1.3) — bug fixes, small changes
- **minor** (e.g. 0.1.2 → 0.2.0) — new features, non-breaking
- **major** (e.g. 0.1.2 → 1.0.0) — breaking changes

Compute the new version number. Show the user: `Current: X.Y.Z → New: A.B.C` and confirm before proceeding.

### Step 3: Bump version

Edit `pyproject.toml` and change the `version` field to the new version.

### Step 4: Commit and tag

```
git add pyproject.toml
git commit -m "Release v{NEW_VERSION}"
git tag v{NEW_VERSION}
```

### Step 5: Push

```
git push origin master
git push origin v{NEW_VERSION}
```

Note: The main branch is `master`. Push both the commit and the tag.

### Step 6: Create GitHub release

```
gh release create v{NEW_VERSION} --title "v{NEW_VERSION}" --generate-notes
```

### Step 7: Watch pipeline

Run `gh run watch` to monitor the CI + publish pipeline. Wait for it to complete.

If the pipeline fails:
1. Report the failure
2. Do NOT delete the tag or release automatically — ask the user what they want to do

### Step 8: Verify

Run `gh run list --limit 3` to confirm the release workflow succeeded.

Tell the user:
- The new version `v{NEW_VERSION}` has been released
- PyPI page: https://pypi.org/project/notebooklm-mcp-2026/{NEW_VERSION}/
- GitHub release: the URL from `gh release view v{NEW_VERSION} --json url`
