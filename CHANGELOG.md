# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Flow animation GIF in README
- Sponsor links: Buy Me a Coffee and Ko-fi (`.github/FUNDING.yml` + README badges)
- `/cleanup-branches` skill for post-merge branch cleanup
- `/sync-docs` skill to keep CLAUDE.md and CHANGELOG.md in sync

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
