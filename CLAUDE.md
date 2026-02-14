# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An MCP (Model Context Protocol) server that lets AI assistants query Google NotebookLM notebooks. Authenticates via Chrome CDP cookie extraction, communicates with Google's internal `batchexecute` RPC API, and exposes 9 tools over stdio JSON-RPC. Built with FastMCP, httpx, and Rich.

## Commands

```bash
# Install
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Test
pytest -v --tb=short
pytest -k "not chrome"              # skip Chrome-dependent tests
pytest tests/test_protocol.py -v    # run one test file
pytest -k "test_build_rpc_body"     # run one test by name

# Run
notebooklm-mcp-2026 serve           # start MCP server (stdio)
notebooklm-mcp-2026 login           # interactive Chrome login
```

## Architecture

5-layer stack, each layer only calls the one below it:

```
MCP Clients (Claude Desktop, etc.)
  └─ server.py        — FastMCP instance + global client singleton (get_client())
       └─ tools/      — 9 tool functions: validate input → call client → return dict
            └─ client.py   — NotebookLMClient: HTTP requests, auth retry, backoff
                 └─ protocol.py  — Pure functions: build RPC bodies, parse responses (zero I/O)
                    auth.py      — Chrome CDP cookie extraction + secure disk storage
```

**Data flow:** MCP JSON-RPC → `server.py` dispatches → tool function → `get_client()` returns singleton → `NotebookLMClient` method → `protocol.build_*()` encodes request → httpx POST → `protocol.parse_*()` decodes → dict response back up the stack.

**Key patterns:**
- `server.get_client()` lazy-initializes a singleton `NotebookLMClient` from disk-cached tokens
- `protocol.py` has zero I/O — all encode/decode functions are pure and directly unit-testable
- 2-layer auth recovery: CSRF refresh first, then full token reload from disk
- All tool functions return `{"status": "success"|"error", ...}` dicts
- All constants live in `config.py` — no other module hardcodes URLs, RPC IDs, headers, or timeouts
- CLI output goes to stderr (stdout reserved for MCP stdio transport)

## Testing

- `conftest.py` provides fixtures: `sample_cookies`, `sample_batchexecute_response`, `sample_query_response`
- `@pytest.mark.chrome` — tests requiring Chrome, auto-skipped in CI
- `@pytest.mark.integration` — integration tests using FastMCP Client
- `asyncio_mode = "auto"` — async tests just work without explicit markers
- `protocol.py` tests need no mocking (pure functions)

## Code Conventions

- Python 3.11+, `from __future__ import annotations` everywhere
- Ruff: line-length 100, target `py311`
- Google-style docstrings (Args, Returns, Raises)
- Custom exceptions in `client.py`: `NotebookJulianError` (base), `AuthenticationError`, `APIError`, `ValidationError`
- Credentials stored at `platformdirs.user_data_dir("notebooklm-mcp-2026")/auth.json` with `0o600` permissions

## Environment Variables

- `NOTEBOOKLM_MCP_DATA_DIR` — override storage directory
- `NOTEBOOKLM_BL` — override Google build label when it rotates
- `NOTEBOOKLM_QUERY_TIMEOUT` — override query timeout (default 120s)

## Release

Use `/release` to run the automated release workflow (lint, test, version bump, git tag, GitHub release, PyPI publish via CI).
