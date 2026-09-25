"""Configuration, paths, and constants for notebooklm-mcp-2026.

All constants are centralized here. No other module should hardcode
API URLs, RPC IDs, headers, or timeouts.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from platformdirs import user_data_dir

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

STORAGE_DIR = Path(
    os.environ.get("NOTEBOOKLM_MCP_DATA_DIR", user_data_dir("notebooklm-mcp-2026"))
)
AUTH_FILE = STORAGE_DIR / "auth.json"
CHROME_PROFILE_DIR = STORAGE_DIR / "chrome-profile"

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

# NotebookLM moved from notebooklm.google.com to notebook.google.com in
# September 2026. The old host now 301-redirects (unauthenticated) or bounces
# to accounts.google.com ServiceLogin (authenticated), so every RPC sent to
# it fails with HTTP 401. Overridable in case Google moves it again.
BASE_URL = os.environ.get("NOTEBOOKLM_BASE_URL", "https://notebook.google.com").rstrip("/")
NOTEBOOKLM_HOST = urlsplit(BASE_URL).hostname or "notebook.google.com"

# Previous hostnames. Used only to recognise an already-open NotebookLM tab;
# never used for API calls, and their host-scoped OSID cookies are NOT valid
# for the current host.
LEGACY_HOSTS = frozenset({"notebooklm.google.com"})

BATCHEXECUTE_URL = f"{BASE_URL}/_/LabsTailwindUi/data/batchexecute"
QUERY_ENDPOINT = (
    "/_/LabsTailwindUi/data/"
    "google.internal.labs.tailwind.orchestration.v1."
    "LabsTailwindOrchestrationService/GenerateFreeFormStreamed"
)

# Build label. The client reads the live value (``cfb2h``) from the
# NotebookLM page on every token refresh; this constant is only the fallback
# used before the first page fetch. ``NOTEBOOKLM_BL`` forces a fixed value.
BUILD_LABEL_OVERRIDE = os.environ.get("NOTEBOOKLM_BL", "")
BUILD_LABEL = BUILD_LABEL_OVERRIDE or "boq_labs-tailwind-frontend_20260923.16_p0"

# ---------------------------------------------------------------------------
# RPC IDs (only the subset needed for our 9 tools)
# ---------------------------------------------------------------------------

RPC_LIST_NOTEBOOKS = "wXbhsf"
RPC_GET_NOTEBOOK = "rLM1Ne"
RPC_GET_SOURCE = "hizoJc"       # Full text content of a source
RPC_ADD_SOURCE = "izAoDd"       # Add URL or text source
RPC_GET_SOURCE_GUIDE = "tr032e" # AI summary + keywords for a source

# ---------------------------------------------------------------------------
# Source type codes (from Google's internal API)
# ---------------------------------------------------------------------------

SOURCE_TYPES: dict[int, str] = {
    1: "google_docs",
    2: "google_slides_sheets",
    3: "pdf",
    4: "pasted_text",
    5: "web_page",
    8: "generated_text",
    9: "youtube",
    11: "uploaded_file",
    13: "image",
    14: "word_doc",
}

# ---------------------------------------------------------------------------
# Authentication — cookie names
# ---------------------------------------------------------------------------

# Minimum cookies required for API calls to succeed
REQUIRED_COOKIES = frozenset({"SID", "HSID", "SSID", "APISID", "SAPISID"})

# Per-service session cookies. Google issues a separate OSID/__Secure-OSID
# for every service host (mail., drive., notebook., notebooklm., ...). Only
# the pair scoped to NOTEBOOKLM_HOST is accepted by NotebookLM; any other
# host's value makes NotebookLM redirect to ServiceLogin?osid=1.
HOST_SCOPED_COOKIES = frozenset({"OSID", "__Secure-OSID"})

# Full set of cookies we keep from Chrome (superset of REQUIRED_COOKIES)
ESSENTIAL_COOKIES = frozenset({
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "OSID", "__Secure-OSID",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    "SIDCC", "__Secure-1PSIDCC", "__Secure-3PSIDCC",
})

# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30.0
SOURCE_ADD_TIMEOUT = 120.0
QUERY_TIMEOUT = float(os.environ.get("NOTEBOOKLM_QUERY_TIMEOUT", "120.0"))

# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
    "X-Same-Domain": "1",
    "User-Agent": USER_AGENT,
}

# Headers that make a page-fetch look like a real browser navigation
PAGE_FETCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0   # seconds
RETRY_MAX_DELAY = 16.0   # seconds
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
