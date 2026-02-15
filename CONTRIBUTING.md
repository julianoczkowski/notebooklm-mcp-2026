# Contributing to notebooklm-mcp-2026

Thanks for your interest in contributing! Here's how to get started.

## Setup

1. Fork and clone the repo
2. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

## Development workflow

1. Create a branch from `master`
2. Make your changes
3. Run lint and tests:
   ```bash
   ruff check src/ tests/
   pytest -v --tb=short
   ```
4. Open a pull request against `master`

## Pull requests

- All PRs require passing CI and an approving review before merging
- Keep PRs focused — one feature or fix per PR
- Include tests for new functionality
- Follow the existing code style (Ruff enforced, line length 100)

## Code style

- Python 3.11+, `from __future__ import annotations` in every file
- Google-style docstrings (Args, Returns, Raises)
- Ruff for linting with `line-length = 100` and `target-version = "py311"`

## Architecture

See [CLAUDE.md](CLAUDE.md) for a detailed overview of the 5-layer architecture and key patterns. The main rule: each layer only calls the one below it.

## Reporting issues

Use the [issue templates](https://github.com/julianoczkowski/notebooklm-mcp-2026/issues/new/choose) for bug reports and feature requests.
