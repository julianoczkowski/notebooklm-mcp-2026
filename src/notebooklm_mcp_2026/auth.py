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

from collections.abc import Callable

from urllib.parse import urlsplit

from .config import (
    AUTH_FILE,
    BASE_URL,
    CHROME_PROFILE_DIR,
    ESSENTIAL_COOKIES,
    HOST_SCOPED_COOKIES,
    LEGACY_HOSTS,
    NOTEBOOKLM_HOST,
    PAGE_FETCH_HEADERS,
    REQUIRED_COOKIES,
    STORAGE_DIR,
)

logger = logging.getLogger("notebooklm_mcp_2026.auth")

NOTEBOOKLM_URL = f"{BASE_URL}/"
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
    build_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthTokens:
        return cls(
            cookies=data.get("cookies", {}),
            csrf_token=data.get("csrf_token", ""),
            session_id=data.get("session_id", ""),
            extracted_at=data.get("extracted_at", 0.0),
            build_label=data.get("build_label", ""),
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


def has_service_cookie(cookies: dict[str, str]) -> bool:
    """Check that a NotebookLM-scoped OSID / __Secure-OSID is present."""
    return bool(HOST_SCOPED_COOKIES & cookies.keys())


def is_notebooklm_url(url: str) -> bool:
    """True if *url* is on the current or a legacy NotebookLM host."""
    host = (urlsplit(url).hostname or "").lower()
    return host == NOTEBOOKLM_HOST or host in LEGACY_HOSTS


def select_auth_cookies(
    raw_cookies: list[dict], host: str = NOTEBOOKLM_HOST
) -> dict[str, str]:
    """Pick the cookies NotebookLM needs from a browser cookie dump.

    Account-wide cookies (``SID``, ``SAPISID``, ``__Secure-1PSIDTS``, ...)
    live on ``.google.com``. The per-service ``OSID`` / ``__Secure-OSID``
    pair is host-only: a signed-in browser holds one per Google service
    (``mail.google.com``, ``drive.google.com``, ``notebooklm.google.com``,
    ``notebook.google.com``, ...). Flattening them by name, as earlier
    versions did, keeps whichever host happened to come last, and
    NotebookLM then answers every request with a redirect to
    ``accounts.google.com/ServiceLogin?osid=1`` (HTTP 401 for RPCs).

    Only ``.google.com`` cookies and cookies scoped exactly to *host* are
    kept; host-scoped cookies from any other host are discarded.
    """
    host = host.lower()
    account_wide: dict[str, str] = {}
    host_scoped: dict[str, str] = {}
    for c in raw_cookies:
        name = c.get("name", "")
        if name not in ESSENTIAL_COOKIES:
            continue
        domain = (c.get("domain") or "").lower()
        if name in HOST_SCOPED_COOKIES:
            if domain.lstrip(".") == host:
                host_scoped[name] = c.get("value", "")
        elif domain in (".google.com", "google.com"):
            account_wide[name] = c.get("value", "")
    return {**account_wide, **host_scoped}


class SessionRejectedError(RuntimeError):
    """Google redirected the cookie session to its sign-in page."""


@dataclass
class PageTokens:
    """Tokens scraped from the NotebookLM page plus rotated cookies."""

    csrf_token: str
    session_id: str
    build_label: str
    cookies: dict[str, str]


def fetch_page_tokens(cookies: dict[str, str], timeout: float = 15.0) -> PageTokens:
    """GET the NotebookLM homepage with *cookies* and scrape its tokens.

    Returns the CSRF token (``SNlM0e``), session ID (``FdrFJe``), live
    build label (``cfb2h``) and the cookie dict updated with any values
    Google rotated in ``Set-Cookie`` (``SIDCC``, ``__Secure-*PSIDTS``, ...).

    Raises:
        SessionRejectedError: Google redirected to its sign-in page.
        RuntimeError: Non-200 response or no CSRF token on the page.
    """
    import httpx

    jar = httpx.Cookies()
    for name, value in cookies.items():
        jar.set(name, value, domain=".google.com")

    with httpx.Client(
        cookies=jar,
        headers=PAGE_FETCH_HEADERS,
        follow_redirects=True,
        timeout=timeout,
    ) as tmp:
        resp = tmp.get(NOTEBOOKLM_URL)
        final_host = (resp.url.host or "").lower()
        if final_host == "accounts.google.com" or resp.url.path.startswith("/login"):
            hops = [f"{h.status_code} {h.url.host}{h.url.path}" for h in resp.history]
            hops.append(f"{resp.status_code} {final_host}{resp.url.path}")
            raise SessionRejectedError(
                "Cookies rejected: NotebookLM redirected to Google sign-in "
                f"({' -> '.join(hops)}). Re-run 'notebooklm-mcp-2026 login'."
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch NotebookLM page: HTTP {resp.status_code}")

        html = resp.text
        csrf = extract_csrf_from_html(html)
        if not csrf:
            raise RuntimeError(
                "Could not extract CSRF token from page. "
                "The page structure may have changed."
            )

        updated = dict(cookies)
        for c in tmp.cookies.jar:
            domain = (c.domain or "").lower()
            if c.name in ESSENTIAL_COOKIES and c.value and (
                domain in (".google.com", "google.com")
                or domain.lstrip(".") == NOTEBOOKLM_HOST
            ):
                updated[c.name] = c.value

        return PageTokens(
            csrf_token=csrf,
            session_id=extract_session_id_from_html(html),
            build_label=extract_build_label_from_html(html),
            cookies=updated,
        )


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


def _remove_stale_locks(profile_dir: Path) -> None:
    """Remove stale Chrome lock files so a fresh instance can start.

    Chrome uses ``SingletonLock`` and ``SingletonSocket`` to enforce one
    instance per user-data-dir. If a previous run crashed or was killed,
    these locks are left behind and cause the next launch to immediately
    delegate to the (dead) "existing" instance and exit.
    """
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        lock = profile_dir / name
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def _get_chrome_launch_args(port: int) -> list[str]:
    """Return Chrome CLI arguments for CDP login (without the executable)."""
    return [
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        "--remote-allow-origins=*",
        NOTEBOOKLM_URL,
    ]


def _wait_for_cdp_connection(port: int, timeout: int) -> None:
    """Poll until a CDP-enabled browser is reachable on *port*."""
    start = time.time()
    while time.time() - start < timeout:
        if _get_debugger_ws_url(port):
            return
        time.sleep(2)
    raise RuntimeError(
        f"No Chrome connection detected on port {port} after {timeout}s. "
        f"Make sure Chrome is running with --remote-debugging-port={port}."
    )


def _launch_chrome(port: int, chrome_path: str | None = None) -> subprocess.Popen:
    """Launch Chrome with remote debugging. Never uses ``shell=True``."""
    global _chrome_process

    resolved = chrome_path or get_chrome_path()
    if not resolved:
        raise RuntimeError(
            "Google Chrome not found. Install Chrome or use --chrome-path."
        )

    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _remove_stale_locks(CHROME_PROFILE_DIR)

    args = [resolved] + _get_chrome_launch_args(port)

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _chrome_process = process

    # Wait for Chrome to start, then verify it's still alive.
    # Chrome exits immediately when it delegates to an existing instance
    # with the same user-data-dir (the "3-second close" problem).
    #
    # On Windows, Chrome uses a multi-process architecture: the launcher
    # process exits with code 0 immediately while the actual browser runs
    # as a detached child process.  In that case the CDP port will still
    # become available, so we treat a code-0 exit as a warning rather
    # than an immediate error and fall through to the CDP check below.
    time.sleep(3)

    exit_code = process.poll()
    if exit_code is not None:
        if exit_code == 0 and _get_debugger_ws_url(port):
            # Windows launcher exited but the browser child is alive and
            # CDP is already responding — continue normally.
            logger.debug("Chrome launcher exited (code 0) but CDP is live — Windows multi-process mode.")
        else:
            stderr_bytes = process.stderr.read() if process.stderr else b""
            stderr_text = stderr_bytes.decode(errors="replace").strip()
            hint = ""
            if stderr_text:
                hint = f"\nChrome stderr: {stderr_text[:500]}"
            raise RuntimeError(
                f"Chrome exited immediately (code {exit_code}). "
                "This usually means another Chrome instance is using the same profile. "
                "Close all Chrome windows and try again, or run:\n"
                f"  rm -rf {CHROME_PROFILE_DIR}/Singleton*"
                f"{hint}"
            )

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
    for pattern in (r'"FdrFJe":"(-?\d+)"', r'f\.sid["\s:=]+["\']?(-?\d+)'):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""


def extract_build_label_from_html(html: str) -> str:
    """Extract the live frontend build label (``cfb2h``) from page HTML."""
    match = re.search(r'"cfb2h":"([^"]+)"', html)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Main authentication flow
# ---------------------------------------------------------------------------


def extract_cookies_via_cdp(
    port: int | None = None,
    login_timeout: int = 300,
    chrome_path: str | None = None,
    on_manual_launch_needed: Callable[[int, list[str]], None] | None = None,
) -> AuthTokens:
    """Launch Chrome, wait for the user to log in, and extract auth tokens.

    This is the primary authentication entry point. It:

    1. Finds an available CDP port.
    2. Launches Chrome pointing at NotebookLM (``config.BASE_URL``).
    3. Waits for the user to complete Google OAuth.
    4. Extracts cookies, CSRF token, and session ID via CDP.
    5. Filters to essential cookies only.
    6. Cleans up the Chrome process in a ``finally`` block.

    If Chrome cannot be found and *on_manual_launch_needed* is provided,
    the callback is invoked with ``(port, launch_args)`` so the caller
    can display instructions for the user to launch Chrome manually.
    The function then waits for a CDP connection before continuing.

    Args:
        port: Explicit port to use (auto-detected if ``None``).
        login_timeout: Maximum seconds to wait for login.
        chrome_path: Explicit path to Chrome/Chromium executable.
        on_manual_launch_needed: Called when Chrome is not found, receives
            ``(port, launch_args)`` so the caller can show manual instructions.

    Returns:
        Populated :class:`AuthTokens`.

    Raises:
        RuntimeError: On Chrome launch failure, login timeout, or extraction error.
    """
    if port is None:
        port = _find_available_port()

    chrome_proc: subprocess.Popen | None = None
    resolved = chrome_path or get_chrome_path()

    try:
        if resolved:
            chrome_proc = _launch_chrome(port, resolved)
        elif on_manual_launch_needed:
            # Chrome not found — let the caller show manual instructions
            CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            _remove_stale_locks(CHROME_PROFILE_DIR)
            on_manual_launch_needed(port, _get_chrome_launch_args(port))
            _wait_for_cdp_connection(port, login_timeout)
        else:
            raise RuntimeError(
                "Google Chrome not found. Install Chrome or use --chrome-path."
            )

        # Find the NotebookLM page
        page = _find_notebooklm_page(port)
        if not page:
            raise RuntimeError("Failed to open NotebookLM page in Chrome.")

        ws_url = page.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("No WebSocket URL for Chrome page — try restarting Chrome.")

        # Wait for login.
        #
        # The URL check alone is unreliable: the NotebookLM host appears
        # briefly before redirecting to accounts.google.com.  Instead, we
        # poll for the *required cookies* to appear — that's the real
        # proof that the user has finished logging in.  We also need the
        # OSID pair scoped to the NotebookLM host, which Google only sets
        # once the browser lands back on that host after sign-in.
        logger.info("Waiting for Google login…")
        start = time.time()
        cookies: dict[str, str] = {}

        while time.time() - start < login_timeout:
            try:
                candidate = select_auth_cookies(_get_page_cookies(ws_url))
                if validate_cookies(candidate):
                    if has_service_cookie(candidate):
                        cookies = candidate
                        break
                    # Signed in to Google but not yet to NotebookLM's host:
                    # land on it so Google issues the host-scoped OSID.
                    if (urlsplit(_get_current_url(ws_url)).hostname or "") != NOTEBOOKLM_HOST:
                        _navigate_to_url(ws_url, NOTEBOOKLM_URL)
            except Exception:
                pass
            time.sleep(5)
        else:
            raise RuntimeError(
                f"Login timed out after {login_timeout}s. "
                "Please log in to NotebookLM in the Chrome window."
            )

        # Navigate back to NotebookLM so we can extract CSRF + session ID
        # from the page HTML (the user may still be on accounts.google.com
        # or a consent screen after cookies are set).
        try:
            current_url = _get_current_url(ws_url)
            if (urlsplit(current_url).hostname or "") != NOTEBOOKLM_HOST:
                _navigate_to_url(ws_url, NOTEBOOKLM_URL)
                time.sleep(3)
        except Exception as exc:
            logger.debug("Could not navigate back to NotebookLM: %s", exc)

        # Extract CSRF and session ID from page HTML
        html = _get_page_html(ws_url)
        csrf_token = extract_csrf_from_html(html)
        session_id = extract_session_id_from_html(html)
        build_label = extract_build_label_from_html(html)

        return AuthTokens(
            cookies=cookies,
            csrf_token=csrf_token,
            session_id=session_id,
            extracted_at=time.time(),
            build_label=build_label,
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


def _find_notebooklm_page(port: int, max_attempts: int = 5) -> dict | None:
    """Find an existing NotebookLM page or create one.

    Retries up to *max_attempts* times with 2-second delays because
    Chrome's CDP endpoint may not be ready immediately after launch.
    """
    import httpx
    from urllib.parse import quote

    for attempt in range(max_attempts):
        pages = _get_pages(port)
        for page in pages:
            if is_notebooklm_url(page.get("url", "")):
                return page

        # If we got pages but none match, try creating a new tab
        if pages:
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

        # CDP not ready yet — wait and retry
        if attempt < max_attempts - 1:
            logger.debug("CDP not ready yet (attempt %d/%d), retrying...", attempt + 1, max_attempts)
            time.sleep(2)

    return None


# ---------------------------------------------------------------------------
# Attach to an already-running, already-signed-in browser
# ---------------------------------------------------------------------------


def extract_tokens_from_browser(cdp_url: str) -> AuthTokens:
    """Read auth cookies from an existing CDP browser, without touching tabs.

    Connects to the browser-level DevTools endpoint at *cdp_url* (for
    example ``http://127.0.0.1:9223`` for a Chromium browser started with
    ``--remote-debugging-port=9223``), reads its cookie store with
    ``Storage.getCookies``, keeps only the NotebookLM-relevant cookies (see
    :func:`select_auth_cookies`), and fetches the CSRF token / session ID /
    build label over plain HTTPS. No tab is opened, navigated, focused, or
    closed, and the browser is left running.

    Raises:
        RuntimeError: Browser unreachable, not signed in to Google, or never
            visited the NotebookLM host (no host-scoped OSID yet).
        SessionRejectedError: Google rejected the extracted session.
    """
    import httpx

    base = cdp_url.rstrip("/")
    try:
        info = httpx.get(f"{base}/json/version", timeout=5).json()
    except Exception as exc:
        raise RuntimeError(f"No DevTools endpoint at {base}: {exc}") from exc
    ws_url = info.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(f"{base}/json/version returned no webSocketDebuggerUrl.")

    raw = execute_cdp_command(ws_url, "Storage.getCookies").get("cookies", [])
    cookies = select_auth_cookies(raw)
    if not validate_cookies(cookies):
        missing = sorted(REQUIRED_COOKIES - cookies.keys())
        raise RuntimeError(
            f"Browser at {base} is not signed in to Google (missing {', '.join(missing)})."
        )
    if not has_service_cookie(cookies):
        raise RuntimeError(
            f"Browser at {base} has no session cookie for {NOTEBOOKLM_HOST}. "
            f"Open {NOTEBOOKLM_URL} in that browser once, then retry."
        )

    page = fetch_page_tokens(cookies)
    return AuthTokens(
        cookies=page.cookies,
        csrf_token=page.csrf_token,
        session_id=page.session_id,
        extracted_at=time.time(),
        build_label=page.build_label,
    )
