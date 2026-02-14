# notebooklm-mcp-2026

Secure MCP server for querying Google NotebookLM notebooks. Designed for use with Claude Code, Cursor, VS Code Copilot, and any MCP-compatible AI assistant.

## What it does

notebooklm-mcp-2026 gives AI assistants direct access to your Google NotebookLM notebooks. It runs as a local subprocess (stdio transport) — no HTTP server needed. Your AI assistant can list your notebooks, read source content, and ask the NotebookLM AI questions about your sources.

## Quick Start

```bash
# 1. Install
pip install notebooklm-mcp-2026
# or with uv:
uv tool install notebooklm-mcp-2026

# 2. Authenticate (one-time — opens Chrome)
notebooklm-mcp-2026 login

# 3. Add to your MCP client (see configuration below)

# 4. Verify it works
notebooklm-mcp-2026 serve  # Should start without errors (Ctrl+C to stop)
```

## Installation

**Requirements:** Python 3.11+, Google Chrome

```bash
# Via pip
pip install notebooklm-mcp-2026

# Via uv (recommended)
uv tool install notebooklm-mcp-2026

# From source
git clone <this-repo>
cd notebooklm-mcp-2026
pip install -e .
```

## Authentication

notebooklm-mcp-2026 uses Google session cookies extracted via Chrome DevTools Protocol. No passwords are stored — only session cookies.

### First-time setup

```bash
notebooklm-mcp-2026 login
```

This will:
1. Launch Chrome pointing at notebooklm.google.com
2. Wait for you to log in to your Google account
3. Extract session cookies via Chrome DevTools Protocol
4. Save them locally with restricted file permissions (`0o600`)

Cookies typically last 2–4 weeks. When they expire, run `notebooklm-mcp-2026 login` again.

### Where credentials are stored

| Platform | Location |
|----------|----------|
| Linux    | `~/.local/share/notebooklm-mcp-2026/auth.json` |
| macOS    | `~/Library/Application Support/notebooklm-mcp-2026/auth.json` |
| Windows  | `%LOCALAPPDATA%\notebooklm-mcp-2026\auth.json` |

Override with: `NOTEBOOKLM_MCP_DATA_DIR=/custom/path`

## MCP Client Configuration

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "notebooklm-mcp-2026": {
      "command": "notebooklm-mcp-2026",
      "args": ["serve"]
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "notebooklm-mcp-2026": {
      "command": "notebooklm-mcp-2026",
      "args": ["serve"]
    }
  }
}
```

### VS Code (Copilot)

Add to VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "notebooklm-mcp-2026": {
        "command": "notebooklm-mcp-2026",
        "args": ["serve"]
      }
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "notebooklm-mcp-2026": {
      "command": "notebooklm-mcp-2026",
      "args": ["serve"]
    }
  }
}
```

## Available Tools (9)

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `login` | Launch Chrome for Google OAuth login | `timeout` (default: 300s) |
| `check_auth` | Verify stored credentials are valid | — |
| `list_notebooks` | List all notebooks with metadata | `max_results` (default: 50) |
| `get_notebook` | Get notebook details + source list | `notebook_id` |
| `list_sources` | List sources in a notebook | `notebook_id` |
| `get_source_content` | Get full text of a source | `source_id` |
| `query_notebook` | Ask the AI a question | `notebook_id`, `query`, `source_ids?`, `conversation_id?` |
| `add_source_url` | Add a URL/YouTube source | `notebook_id`, `url` |
| `add_source_text` | Add pasted text source | `notebook_id`, `text`, `title?` |

### Typical workflow

```
1. list_notebooks          → find the notebook ID you want
2. list_sources            → see what sources are in it
3. query_notebook          → ask questions about the sources
4. get_source_content      → read raw source text if needed
```

### Follow-up conversations

`query_notebook` returns a `conversation_id`. Pass it back to ask follow-up questions in the same conversation context:

```
# First question
result = query_notebook(notebook_id="abc", query="What is the main topic?")
# result.conversation_id = "uuid-123"

# Follow-up
result = query_notebook(notebook_id="abc", query="Tell me more about that", conversation_id="uuid-123")
```

## Troubleshooting

### "Not authenticated" error
Run `notebooklm-mcp-2026 login` in your terminal.

### "Cookies expired" error
Session cookies have a limited lifespan (2–4 weeks). Run `notebooklm-mcp-2026 login` again.

### "Chrome not found" error
Install Google Chrome. On Linux, ensure `google-chrome` or `chromium` is in your PATH.

### Empty notebook list
Make sure you're logged into the correct Google account that has NotebookLM notebooks.

### "Build label" errors
Google occasionally rotates their build label. Set the updated label:
```bash
NOTEBOOKLM_BL="boq_labs-tailwind-frontend_YYYYMMDD.XX_p0" notebooklm-mcp-2026 serve
```

### Rate limit errors
NotebookLM free tier allows ~50 queries per day. Wait until the next day or upgrade.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTEBOOKLM_MCP_DATA_DIR` | Platform default | Override data storage location |
| `NOTEBOOKLM_BL` | `boq_labs-tailwind-frontend_20260108.06_p0` | Google build label |
| `NOTEBOOKLM_QUERY_TIMEOUT` | `120.0` | Query timeout in seconds |

## Security

- **No passwords stored** — only Google session cookies
- **File permissions** — credentials saved with `0o600` (owner read/write only)
- **Directory permissions** — data directory created with `0o700` (owner only)
- **No `eval`/`exec`** — no dynamic code execution anywhere
- **No `shell=True`** — Chrome launched with explicit argument lists
- **Cookie filtering** — only essential Google auth cookies are persisted
- **Chrome cleanup** — Chrome process always terminated in `finally` blocks
- **Input validation** — all tool parameters validated before use
- **Timeouts** — all HTTP requests have explicit timeouts
- **CSRF protection** — tokens passed in request body, auto-refreshed on expiry

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

## License

MIT
