# Architecture

## Layer Diagram

```
┌─────────────────────────────────────────────────┐
│  MCP Clients (Claude Code, Cursor, VS Code)     │
│  Connect via stdio — no HTTP server needed       │
└──────────────────────┬──────────────────────────┘
                       │ JSON-RPC over stdin/stdout
┌──────────────────────▼──────────────────────────┐
│  server.py — FastMCP server + CLI entry point    │
│  • Registers 9 tools                             │
│  • Global get_client() singleton                 │
│  • argparse: serve | login | version             │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  tools/ — 9 MCP tool functions                   │
│  • auth_tools.py: login, check_auth              │
│  • notebooks.py: list_notebooks, get_notebook    │
│  • sources.py: list/get/add sources              │
│  • query.py: query_notebook                      │
│  All tools return dict[str, Any] with status key │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  client.py — NotebookLMClient                    │
│  • HTTP client (httpx) with cookie auth          │
│  • Auth retry: CSRF refresh + disk reload        │
│  • Server retry: exponential backoff on 5xx/429  │
│  • Domain methods: notebooks, sources, query     │
│  • Conversation cache for follow-ups             │
└────────┬─────────────────────────┬──────────────┘
         │                         │
┌────────▼────────┐  ┌────────────▼──────────────┐
│  protocol.py    │  │  auth.py                   │
│  Pure functions │  │  Chrome CDP cookie extract  │
│  • Encode RPC   │  │  • Credential storage       │
│  • Decode resp  │  │  • Token validation          │
│  • Parse query  │  │  • Chrome lifecycle          │
│  No I/O         │  │  Secure file permissions     │
└────────┬────────┘  └────────────┬──────────────┘
         │                         │
┌────────▼─────────────────────────▼──────────────┐
│  config.py — Constants, paths, RPC IDs           │
│  • No dependencies on other modules              │
│  • Single source of truth for all constants      │
└─────────────────────────────────────────────────┘
```

## Module Descriptions

### `config.py`
All constants centralized in one file:
- **Paths**: `STORAGE_DIR`, `AUTH_FILE`, `CHROME_PROFILE_DIR` (via platformdirs)
- **API**: `BASE_URL`, `BATCHEXECUTE_URL`, `QUERY_ENDPOINT`, `BUILD_LABEL`
- **RPC IDs**: `RPC_LIST_NOTEBOOKS`, `RPC_GET_NOTEBOOK`, `RPC_GET_SOURCE`, `RPC_ADD_SOURCE`, `RPC_GET_SOURCE_GUIDE`
- **Auth**: `REQUIRED_COOKIES`, `ESSENTIAL_COOKIES`
- **HTTP**: `DEFAULT_HEADERS`, `PAGE_FETCH_HEADERS`, `USER_AGENT`
- **Retry**: `MAX_RETRIES`, `RETRY_BASE_DELAY`, `RETRYABLE_STATUS_CODES`
- **Timeouts**: `DEFAULT_TIMEOUT`, `SOURCE_ADD_TIMEOUT`, `QUERY_TIMEOUT`

### `protocol.py`
Pure functions for Google's batchexecute RPC protocol. No I/O, no state, fully testable.

**Request encoding:**
1. JSON-encode params with compact separators
2. Wrap in `[[[rpc_id, params_json, None, "generic"]]]`
3. URL-encode the whole thing
4. Format: `f.req={encoded}&at={csrf_token}&`

**Response decoding:**
1. Strip `)]}'` anti-XSSI prefix
2. Parse newline-separated chunks (byte count + JSON lines)
3. Find `["wrb.fr", "rpc_id", "<result_json>", ...]`
4. Detect Error 16 (auth expired) → raise `AuthExpiredError`

**Query endpoint:**
Uses a different URL and envelope format. Response chunks have type indicators:
- Type 1 = actual answer (preferred)
- Type 2 = thinking step (fallback)

### `auth.py`
Authentication via Chrome DevTools Protocol:

1. **`extract_cookies_via_cdp()`**: Main auth flow
   - Find available port (9222–9231)
   - Launch Chrome with `--remote-debugging-port`
   - Wait for user login (poll URL every 5s)
   - Extract cookies via `Network.getAllCookies`
   - Extract CSRF from HTML: `"SNlM0e":"<token>"`
   - Extract session ID: `"FdrFJe":"<id>"`
   - Filter to essential cookies
   - Cleanup Chrome in `finally`

2. **Credential storage**: `save_tokens()` / `load_tokens()`
   - JSON file at `~/.local/share/notebooklm-mcp-2026/auth.json`
   - File permissions: `0o600`
   - Directory permissions: `0o700`

### `client.py`
`NotebookLMClient` — the single HTTP interface to Google's servers.

**Auth recovery (2-layer):**
1. Refresh CSRF token (fetch homepage, extract from HTML)
2. Reload cookies from disk (user may have re-logged in)

**Server error retry:**
- HTTP 429, 500, 502, 503, 504
- Exponential backoff: 1s, 2s, 4s (up to 16s)
- Max 3 retries

**Domain methods:**
- `list_notebooks()` → RPC `wXbhsf`
- `get_notebook(id)` → RPC `rLM1Ne`
- `list_sources(notebook_id)` → via `get_notebook`
- `get_source_content(source_id)` → RPC `hizoJc`
- `query(notebook_id, query, ...)` → Streaming endpoint
- `add_url_source(notebook_id, url)` → RPC `izAoDd`
- `add_text_source(notebook_id, text, title)` → RPC `izAoDd`

### `server.py`
FastMCP server with stdio transport:
- Registers all 9 tools from `tools/` subpackage
- Global `get_client()` singleton (lazy initialization from cached tokens)
- CLI: `notebooklm-mcp-2026 serve` (default), `notebooklm-mcp-2026 login`, `notebooklm-mcp-2026 version`

### `tools/`
Each tool function:
1. Gets the client via `server.get_client()`
2. Validates input parameters
3. Calls the appropriate `client.method()`
4. Returns `dict[str, Any]` with `"status": "success"|"error"`
5. Catches all exceptions and returns user-friendly messages

## Data Flow: Query Example

```
User asks: "What is the main topic of my notebook?"
    │
    ▼
MCP Client sends JSON-RPC → server.py (stdio)
    │
    ▼
query_notebook() tool (tools/query.py)
    │ validates notebook_id and query
    ▼
get_client() → NotebookLMClient singleton
    │
    ▼
client.query(notebook_id, query_text)
    │ 1. If no source_ids: calls get_notebook() to find them
    │ 2. Builds conversation params
    │ 3. Uses protocol.build_query_body() + build_query_url()
    ▼
httpx.Client.post() → Google's streaming endpoint
    │
    ▼
protocol.parse_query_response(response.text)
    │ Strips )]}'  prefix
    │ Parses chunks
    │ Finds longest type-1 (answer) text
    ▼
Returns: {answer, conversation_id, turn_number, is_follow_up}
    │
    ▼
JSON-RPC response → MCP Client → User sees the answer
```

## Security Model

### What we store
- Google session cookies (essential set only, ~15 cookies)
- CSRF token (auto-refreshed)
- Session ID (auto-refreshed)
- Chrome profile directory (for persistent login)

### What we never store
- Google account password
- OAuth tokens (we use cookie-based session auth)
- Any user data or notebook content

### File security
- `auth.json`: mode `0o600` (owner read/write only)
- Data directory: mode `0o700` (owner only)
- Chrome profile: standard Chrome permissions

### Code security
- No `eval()`, `exec()`, or `compile()` anywhere
- No `subprocess.Popen(shell=True)` — always explicit arg lists
- No `pickle` or unsafe deserialization
- No string interpolation in URLs or selectors (all parameterized)
- All HTTP requests have explicit timeouts
- CSRF token in POST body, never in URL query string

### Chrome lifecycle
- Launched with minimal flags (no extensions, no first-run)
- Profile isolated to notebooklm-mcp-2026 directory
- Always terminated in `finally` blocks
- `atexit` handler as safety net
