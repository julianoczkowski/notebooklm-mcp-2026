"""Authentication — Chrome CDP cookie extraction and credential storage.

Security model:
- Data directory created with 0o700 (owner-only access).
- Credential file written with 0o600 (owner read/write only).
- Chrome launched via ``subprocess.Popen(list)`` — never ``shell=True``.
- Chrome process always cleaned up in ``finally`` blocks.
- Only essential Google cookies are persisted (not the full cookie jar).
"""

from __future__ import annotations

import atexit
import json
import logging
import platform
import re
import shutil
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    AUTH_FILE,
    CHROME_PROFILE_DIR,
    ESSENTIAL_COOKIES,
    REQUIRED_COOKIES,
    STORAGE_DIR,
)

logger = logging.getLogger("notebook_julian.auth")

NOTEBOOKLM_URL = "https://notebooklm.google.com/"
CDP_PORT_START = 9222
CDP_PORT_RANGE = 10  # scan 9222–9231


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AuthTokens:
    """Persisted authentication state."""

    cookies: dict[str, str]
    csrf_token: str = ""
    session_id: str = ""
    extracted_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthTokens:
        return cls(
            cookies=data.get("cookies", {}),
            csrf_token=data.get("csrf_token", ""),
            session_id=data.get("session_id", ""),
            extracted_at=data.get("extracted_at", 0.0),
        )


# ---------------------------------------------------------------------------
# Credential storage (file-based, secure permissions)
# ---------------------------------------------------------------------------


def ensure_storage_dir() -> Path:
    """Create the storage directory with owner-only permissions."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STORAGE_DIR.chmod(0o700)
    except OSError:
        pass  # Windows doesn't support Unix permissions
    return STORAGE_DIR


def save_tokens(tokens: AuthTokens) -> None:
    """Write tokens to disk with restricted permissions (0o600)."""
    ensure_storage_dir()
    AUTH_FILE.write_text(json.dumps(tokens.to_dict(), indent=2))
    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass


def load_tokens() -> AuthTokens | None:
    """Load tokens from disk. Returns ``None`` if missing or corrupt."""
    if not AUTH_FILE.exists():
        return None
    try:
        data = json.loads(AUTH_FILE.read_text())
        tokens = AuthTokens.from_dict(data)
        if not tokens.cookies:
            return None
        return tokens
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def validate_cookies(cookies: dict[str, str]) -> bool:
    """Check that all required Google auth cookies are present."""
    return REQUIRED_COOKIES.issubset(cookies.keys())


# ---------------------------------------------------------------------------
# Chrome discovery
# ---------------------------------------------------------------------------


def get_chrome_path() -> str | None:
    """Return the Chrome executable path for the current platform."""
    system = platform.system()
    if system == "Darwin":
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return path if Path(path).exists() else None
    elif system == "Linux":
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                return found
        return None
    elif system == "Windows":
        path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        return path if Path(path).exists() else None
    return None


def _find_available_port() -> int:
    """Find an available TCP port in the CDP range."""
    for offset in range(CDP_PORT_RANGE):
        port = CDP_PORT_START + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"No available ports in range {CDP_PORT_START}–{CDP_PORT_START + CDP_PORT_RANGE - 1}. "
        "Close some applications and try again."
    )


# ---------------------------------------------------------------------------
# Chrome lifecycle
# ---------------------------------------------------------------------------

# Module-level reference so atexit can clean up
_chrome_process: subprocess.Popen | None = None


def _cleanup_chrome() -> None:
    """atexit handler — terminate Chrome if still running."""
    global _chrome_process
    if _chrome_process is not None:
        try:
            _chrome_process.terminate()
            _chrome_process.wait(timeout=5)
        except Exception:
            try:
                _chrome_process.kill()
            except Exception:
                pass
        _chrome_process = None


atexit.register(_cleanup_chrome)


def _launch_chrome(port: int) -> subprocess.Popen:
    """Launch Chrome with remote debugging. Never uses ``shell=True``."""
    global _chrome_process

    chrome_path = get_chrome_path()
    if not chrome_path:
        raise RuntimeError(
            "Google Chrome not found. Install Chrome or set the path manually."
        )

    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        "--remote-allow-origins=*",
        NOTEBOOKLM_URL,
    ]

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _chrome_process = process
    time.sleep(3)  # Wait for Chrome to initialise
    return process


# ---------------------------------------------------------------------------
# Chrome DevTools Protocol helpers
# ---------------------------------------------------------------------------


def _get_debugger_ws_url(port: int) -> str | None:
    """Get the browser-level WebSocket debugger URL."""
    import httpx

    try:
        resp = httpx.get(f"http://localhost:{port}/json/version", timeout=5)
        return resp.json().get("webSocketDebuggerUrl")
    except Exception:
        return None


def _get_pages(port: int) -> list[dict]:
    """List open pages via CDP HTTP API."""
    import httpx

    try:
        resp = httpx.get(f"http://localhost:{port}/json", timeout=5)
        return resp.json()
    except Exception:
        return []


def execute_cdp_command(ws_url: str, method: str, params: dict | None = None) -> dict:
    """Execute a single CDP command over WebSocket and return the result."""
    import websocket

    try:
        ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
    except TypeError:
        ws = websocket.create_connection(ws_url, timeout=30)

    try:
        command = {"id": 1, "method": method, "params": params or {}}
        ws.send(json.dumps(command))
        while True:
            response = json.loads(ws.recv())
            if response.get("id") == 1:
                return response.get("result", {})
    finally:
        ws.close()


def _get_page_cookies(ws_url: str) -> list[dict]:
    """Extract all cookies via ``Network.getAllCookies``."""
    result = execute_cdp_command(ws_url, "Network.getAllCookies")
    return result.get("cookies", [])


def _get_page_html(ws_url: str) -> str:
    """Get the page HTML via ``Runtime.evaluate``."""
    execute_cdp_command(ws_url, "Runtime.enable")
    result = execute_cdp_command(
        ws_url,
        "Runtime.evaluate",
        {"expression": "document.documentElement.outerHTML"},
    )
    return result.get("result", {}).get("value", "")


def _get_current_url(ws_url: str) -> str:
    """Get the current page URL."""
    execute_cdp_command(ws_url, "Runtime.enable")
    result = execute_cdp_command(
        ws_url,
        "Runtime.evaluate",
        {"expression": "window.location.href"},
    )
    return result.get("result", {}).get("value", "")


def _navigate_to_url(ws_url: str, url: str) -> None:
    """Navigate the page to *url* and wait for it to load."""
    execute_cdp_command(ws_url, "Page.enable")
    execute_cdp_command(ws_url, "Page.navigate", {"url": url})
    time.sleep(3)


# ---------------------------------------------------------------------------
# Token extraction helpers
# ---------------------------------------------------------------------------


def extract_csrf_from_html(html: str) -> str:
    """Extract the CSRF token (``SNlM0e``) from page HTML."""
    match = re.search(r'"SNlM0e":"([^"]+)"', html)
    return match.group(1) if match else ""


def extract_session_id_from_html(html: str) -> str:
    """Extract the session ID (``FdrFJe``) from page HTML."""
    for pattern in (r'"FdrFJe":"(\d+)"', r'f\.sid["\s:=]+["\']?(\d+)'):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""


# ---------------------------------------------------------------------------
# Main authentication flow
# ---------------------------------------------------------------------------


def extract_cookies_via_cdp(
    port: int | None = None,
    login_timeout: int = 300,
) -> AuthTokens:
    """Launch Chrome, wait for the user to log in, and extract auth tokens.

    This is the primary authentication entry point. It:

    1. Finds an available CDP port.
    2. Launches Chrome pointing at notebooklm.google.com.
    3. Waits for the user to complete Google OAuth.
    4. Extracts cookies, CSRF token, and session ID via CDP.
    5. Filters to essential cookies only.
    6. Cleans up the Chrome process in a ``finally`` block.

    Args:
        port: Explicit port to use (auto-detected if ``None``).
        login_timeout: Maximum seconds to wait for login.

    Returns:
        Populated :class:`AuthTokens`.

    Raises:
        RuntimeError: On Chrome launch failure, login timeout, or extraction error.
    """
    if port is None:
        port = _find_available_port()

    chrome_proc: subprocess.Popen | None = None

    try:
        chrome_proc = _launch_chrome(port)

        # Find the NotebookLM page
        page = _find_notebooklm_page(port)
        if not page:
            raise RuntimeError("Failed to open NotebookLM page in Chrome.")

        ws_url = page.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("No WebSocket URL for Chrome page — try restarting Chrome.")

        # Wait for login
        current_url = _get_current_url(ws_url)
        if "notebooklm.google.com" not in current_url:
            _navigate_to_url(ws_url, NOTEBOOKLM_URL)
            current_url = _get_current_url(ws_url)

        if "accounts.google.com" in current_url or "notebooklm.google.com" not in current_url:
            logger.info("Waiting for Google login…")
            start = time.time()
            while time.time() - start < login_timeout:
                time.sleep(5)
                try:
                    current_url = _get_current_url(ws_url)
                    if "notebooklm.google.com" in current_url:
                        break
                except Exception:
                    pass
            else:
                raise RuntimeError(
                    f"Login timed out after {login_timeout}s. "
                    "Please log in to NotebookLM in the Chrome window."
                )

        # Give the page a moment to fully load after login redirect
        time.sleep(2)

        # Extract cookies
        raw_cookies = _get_page_cookies(ws_url)
        if not raw_cookies:
            raise RuntimeError("No cookies extracted — make sure you are fully logged in.")

        # Filter to essential Google cookies on .google.com domain
        cookies: dict[str, str] = {}
        for c in raw_cookies:
            name = c.get("name", "")
            domain = c.get("domain", "")
            if name in ESSENTIAL_COOKIES and ".google.com" in domain:
                cookies[name] = c.get("value", "")

        if not validate_cookies(cookies):
            missing = REQUIRED_COOKIES - cookies.keys()
            raise RuntimeError(
                f"Missing required cookies: {', '.join(sorted(missing))}. "
                "Make sure you are fully logged in."
            )

        # Extract CSRF and session ID from page HTML
        html = _get_page_html(ws_url)
        csrf_token = extract_csrf_from_html(html)
        session_id = extract_session_id_from_html(html)

        return AuthTokens(
            cookies=cookies,
            csrf_token=csrf_token,
            session_id=session_id,
            extracted_at=time.time(),
        )

    finally:
        # Always clean up Chrome
        global _chrome_process
        proc = chrome_proc or _chrome_process
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            if _chrome_process is proc:
                _chrome_process = None


def _find_notebooklm_page(port: int) -> dict | None:
    """Find an existing NotebookLM page or create one."""
    import httpx
    from urllib.parse import quote

    pages = _get_pages(port)
    for page in pages:
        if "notebooklm.google.com" in page.get("url", ""):
            return page

    # Create a new tab
    try:
        encoded = quote(NOTEBOOKLM_URL, safe="")
        resp = httpx.put(f"http://localhost:{port}/json/new?{encoded}", timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            return resp.json()

        # Fallback: blank tab + navigate
        resp = httpx.put(f"http://localhost:{port}/json/new", timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            page = resp.json()
            ws_url = page.get("webSocketDebuggerUrl")
            if ws_url:
                _navigate_to_url(ws_url, NOTEBOOKLM_URL)
            return page
    except Exception:
        pass

    return None
