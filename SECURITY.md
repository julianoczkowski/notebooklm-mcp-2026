# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue.**
2. Use [GitHub Security Advisories](../../security/advisories/new) to report privately.
3. Include: description, reproduction steps, potential impact.
4. Expected response time: 48 hours.

## Threat Model

### What this tool does

notebooklm-mcp-2026 acts as a local bridge between MCP clients (Claude Code, Cursor, etc.) and Google's NotebookLM service. It authenticates using Google session cookies extracted from your Chrome browser.

### Trust boundaries

- **Local machine is trusted.** Credentials are stored on disk with restrictive permissions. Anyone with access to your user account can read them.
- **Google's servers are trusted.** All API communication goes to `notebooklm.google.com` over HTTPS.
- **MCP clients are trusted.** The server exposes all 9 tools to any MCP client that connects over stdio.
- **Network is untrusted.** All HTTP requests use HTTPS. No plaintext connections.

### What we protect against

- **Credential leakage** — cookies stored with `0o600` permissions, directory with `0o700`
- **Command injection** — Chrome launched with explicit argument lists, never `shell=True`
- **Code injection** — no `eval()`, `exec()`, `compile()`, or `pickle`
- **CSRF exposure** — tokens passed in POST body, never in URL query strings
- **Stale processes** — Chrome process always terminated in `finally` blocks
- **Cookie over-collection** — only essential Google auth cookies are persisted (15 out of 100+)

### What we do NOT protect against

- **Local privilege escalation** — if an attacker has access to your user account, they can read `auth.json`
- **Malicious MCP clients** — any client connected via stdio can call all 9 tools
- **Google account compromise** — if your Google account is compromised, this tool's cookies are also compromised
- **Memory inspection** — cookies and tokens exist in process memory during execution

## Credential Lifecycle

| Stage | What happens |
|-------|-------------|
| Login | Chrome opens, user logs in, cookies extracted via CDP, saved to `auth.json` |
| Usage | Cookies sent with each API request; CSRF token auto-refreshed as needed |
| Expiry | Cookies expire in 2-4 weeks; user must re-run `login` |
| Logout | `auth.json` and Chrome profile directory are deleted |

There is no long-lived refresh token. When cookies expire, re-authentication via Chrome is required.

## What we store

- Google session cookies (essential set only, ~15 cookies)
- CSRF token (auto-refreshed on expiry)
- Session ID (auto-refreshed on expiry)

## What we never store

- Google account passwords
- OAuth tokens
- User data or notebook content

## File security

- `auth.json`: mode `0o600` (owner read/write only)
- Data directory: mode `0o700` (owner only)
- Platform-specific storage via `platformdirs`

## Code security

- No `eval()`, `exec()`, or `compile()`
- No `subprocess.Popen(shell=True)` — Chrome launched with explicit argument lists
- No `pickle` or unsafe deserialization
- All HTTP requests have explicit timeouts
- CSRF token in POST body, never in URL query string
- Chrome process always terminated in `finally` blocks
