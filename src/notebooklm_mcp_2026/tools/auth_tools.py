"""Authentication tools — login and check_auth."""

from __future__ import annotations

import time
from typing import Any


def login(timeout: int = 300) -> dict[str, Any]:
    """Launch Chrome for Google login and extract authentication cookies.

    This opens a Chrome window where you log in to your Google account.
    After successful login, cookies are extracted automatically via the
    Chrome DevTools Protocol and saved locally.

    **This tool is interactive** — it blocks until you complete login or
    the timeout expires.

    Args:
        timeout: Maximum seconds to wait for login (default: 300).

    Returns:
        Status dict with cookie count on success, or error message.
    """
    from ..auth import extract_cookies_via_cdp, save_tokens

    try:
        tokens = extract_cookies_via_cdp(login_timeout=timeout)
        save_tokens(tokens)
        return {
            "status": "success",
            "message": f"Authenticated successfully. Saved {len(tokens.cookies)} cookies.",
            "has_csrf": bool(tokens.csrf_token),
            "has_session_id": bool(tokens.session_id),
        }
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Login failed: {e}"}


def check_auth() -> dict[str, Any]:
    """Check if stored credentials are valid.

    Loads saved tokens from disk and attempts to validate them by
    fetching the NotebookLM homepage. No browser window is needed.

    Returns:
        Status dict indicating authenticated, expired, or not found.
    """
    from ..auth import load_tokens

    tokens = load_tokens()
    if tokens is None:
        return {
            "status": "not_authenticated",
            "message": "No saved credentials found. Run 'notebooklm-mcp-2026 login' first.",
        }

    # Try to validate by refreshing the CSRF token
    from ..client import NotebookLMClient, AuthenticationError

    try:
        client = NotebookLMClient(
            cookies=tokens.cookies,
            csrf_token=tokens.csrf_token,
            session_id=tokens.session_id,
        )
        client.close()

        age_hours = (time.time() - tokens.extracted_at) / 3600
        return {
            "status": "authenticated",
            "message": "Credentials are valid.",
            "cookie_count": len(tokens.cookies),
            "age_hours": round(age_hours, 1),
        }
    except AuthenticationError as e:
        return {
            "status": "expired",
            "message": str(e),
            "hint": "Run 'notebooklm-mcp-2026 login' to re-authenticate.",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Validation failed: {e}",
        }
