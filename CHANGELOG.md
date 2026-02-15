# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
