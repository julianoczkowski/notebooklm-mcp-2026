# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Automatic session refresh. Google stops accepting the extracted
  `__Secure-1PSIDTS` cookie about two hours after login, and `RotateCookies`
  from a plain HTTP client never returns a new one, so the server used to need
  `login` several times a day. When a call fails on a dead session, the client
  now re-extracts cookies from the login Chrome profile in headless mode
  (`auth.refresh_tokens_headless`, about 20 seconds, no window), saves them and
  retries. Newer tokens on disk are still preferred; a failed refresh is not
  retried for 10 minutes; `NOTEBOOKLM_AUTO_REFRESH=0` turns it off

### Changed
- README: cookies were documented as lasting 2–4 weeks; the saved session
  actually lasts about two hours

### Fixed
- NotebookLM moved to `notebook.google.com` (rebranded "Gemini Notebook");
  `notebooklm.google.com` now 301-redirects there. Every call failed with
  "Authentication expired after retry." even right after `login`. The server
  now targets the new host (`config.NOTEBOOKLM_HOST`) and the default build
  label is `boq_labs-tailwind-frontend_20261005.13_p0`
- Login kept the wrong `OSID` cookie: cookies were picked by name, so the
  host-only `OSID` from `accounts.google.com` or the old host could win and
  the new host served a signed-out page. `select_essential_cookies` keeps only
  domain-wide cookies and the NotebookLM host's own, and login re-reads them
  after the NotebookLM page has loaded
- Session IDs (`FdrFJe`) can be negative; they were silently dropped

## [0.2.1] - 2026-05-01

### Added
- Flow animation GIF in README
- Sponsor links: Buy Me a Coffee and Ko-fi (`.github/FUNDING.yml` + README badges)
- `/cleanup-branches` skill for post-merge branch cleanup
- `/sync-docs` skill to keep CLAUDE.md and CHANGELOG.md in sync
- Unit tests for `_launch_chrome` covering Windows multi-process launcher behavior

### Fixed
- Windows Chrome login crash: launcher process exits with code 0 immediately
  while the browser runs as a detached child. `_launch_chrome` now treats a
  code-0 exit as success when CDP is reachable, so login no longer fails on
  Windows (#19, thanks @WillWetzel)

## [0.2.0] - 2026-02-15

### Added
- Windows CI (ubuntu, macos, windows matrix)
- Code coverage with pytest-cov
- `--debug` flag on all CLI subcommands
- `--dry-run` flag on `setup` command
- Pre-commit hooks (ruff check + ruff format)
- Unit tests for all 9 MCP tool functions (`test_tools.py`)
- Example scripts (`examples/basic_workflow.py`, `examples/follow_up_conversation.py`)
- SECURITY.md with threat model and trust boundaries
- CONTRIBUTING.md, CODE_OF_CONDUCT.md, CHANGELOG.md
- CODEOWNERS, PR template, issue templates
- Dependabot for pip and GitHub Actions dependencies
- `[project.urls]` in pyproject.toml (Homepage, Repository, Issues, Changelog)
- Example JSON outputs in README
- "Getting Help" section in README

### Changed
- Improved error messages: rate limit hints, doctor command suggestions
- Hero image in README updated and set to full width

## [0.1.2] - 2026-02-14

### Added
- Branded help screen as default CLI command

### Fixed
- Ruff lint: removed extraneous f-string prefix

## [0.1.1] - 2026-02-14

### Added
- `logout` command to clear stored credentials
- Platform-specific prerequisites in README

### Changed
- Rewrote README for zero-friction onboarding
- Recommend `pipx` as primary install method

## [0.1.0] - 2026-02-14

### Added
- Initial release
- MCP server with 9 tools for querying NotebookLM notebooks
- Chrome CDP cookie extraction for authentication
- Branded CLI with `serve`, `login`, `status`, and `doctor` commands
- CI/CD pipelines for testing and PyPI publishing
