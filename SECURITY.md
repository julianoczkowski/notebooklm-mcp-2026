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

## Security Model

### What we store

- Google session cookies (essential set only, ~15 cookies)
- CSRF token (auto-refreshed on expiry)
- Session ID (auto-refreshed on expiry)

### What we never store

- Google account passwords
- OAuth tokens
- User data or notebook content

### File security

- `auth.json`: mode `0o600` (owner read/write only)
- Data directory: mode `0o700` (owner only)
- Platform-specific storage via `platformdirs`

### Code security

- No `eval()`, `exec()`, or `compile()`
- No `subprocess.Popen(shell=True)` — Chrome launched with explicit argument lists
- No `pickle` or unsafe deserialization
- All HTTP requests have explicit timeouts
- CSRF token in POST body, never in URL query string
- Chrome process always terminated in `finally` blocks

## Credential Lifecycle

Cookies expire in 2-4 weeks. Users must re-authenticate via
`notebooklm-mcp-2026 login`. There is no long-lived refresh token.
