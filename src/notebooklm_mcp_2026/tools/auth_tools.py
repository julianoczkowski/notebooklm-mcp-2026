"""Authentication tools — login and check_auth."""

from __future__ import annotations

import time
from typing import Any


def login(timeout: int = 300, cdp_url: str = "") -> dict[str, Any]:
    """Launch Chrome for Google login and extract authentication cookies.

    If ``cdp_url`` (or the ``NOTEBOOKLM_CDP_URL`` env var) is set, no browser
    is launched: cookies are read from that already-running, signed-in
    browser's DevTools endpoint instead, without opening or touching tabs.

    This opens a Chrome window where you log in to your Google account.
    After successful login, cookies are extracted automatically via the
    Chrome DevTools Protocol and saved locally.

    **This tool is interactive** — it blocks until you complete login or
    the timeout expires.

    Args:
        timeout: Maximum seconds to wait for login (default: 300).
        cdp_url: DevTools URL of an already signed-in browser, e.g.
            ``http://127.0.0.1:9223``.

    Returns:
        Status dict with cookie count on success, or error message.
    """
    import os

    from ..auth import extract_cookies_via_cdp, extract_tokens_from_browser, save_tokens
    from ..server import reset_client

    cdp_url = cdp_url or os.environ.get("NOTEBOOKLM_CDP_URL", "")
    try:
        if cdp_url:
            tokens = extract_tokens_from_browser(cdp_url)
        else:
            tokens = extract_cookies_via_cdp(login_timeout=timeout)
        save_tokens(tokens)
        reset_client()  # drop the cached client holding the old session
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

    Loads saved tokens from disk and validates them with a real, read-only
    API call (list notebooks). Only a successful RPC counts as
    authenticated; a stored CSRF token or a 200 homepage is not proof.

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
            build_label=tokens.build_label,
        )
        try:
            notebooks = client.list_notebooks()
        finally:
            client.close()

        age_hours = (time.time() - tokens.extracted_at) / 3600
        return {
            "status": "authenticated",
            "message": "Credentials are valid (list_notebooks succeeded).",
            "notebook_count": len(notebooks),
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
