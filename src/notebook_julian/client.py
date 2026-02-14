"""NotebookLM HTTP API client.

This module is the single point of contact with Google's servers. It uses
the :mod:`protocol` module for encoding/decoding and the :mod:`auth` module
for credential management.

Retry strategy:
- HTTP 401/403 or RPC Error 16 → refresh CSRF token, retry once.
- HTTP 429/5xx → exponential backoff, up to ``MAX_RETRIES`` attempts.
- All other errors → fail immediately.
"""

from __future__ import annotations

import logging
import random
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from . import config
from .auth import (
    AuthTokens,
    extract_csrf_from_html,
    extract_session_id_from_html,
    load_tokens,
    save_tokens,
)
from .protocol import (
    AuthExpiredError,
    build_query_body,
    build_query_url,
    build_request_body,
    build_url,
    extract_rpc_result,
    parse_query_response,
    parse_response,
)

logger = logging.getLogger("notebook_julian.client")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NotebookJulianError(Exception):
    """Base exception for all notebook-julian errors."""


class AuthenticationError(NotebookJulianError):
    """Authentication failure — cookies expired or CSRF invalid."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint or "Run 'notebook-julian login' to re-authenticate."


class APIError(NotebookJulianError):
    """An API call failed (network, parsing, unexpected response)."""


class ValidationError(NotebookJulianError):
    """Input validation failure."""


# ---------------------------------------------------------------------------
# Conversation turn (for follow-up queries)
# ---------------------------------------------------------------------------


@dataclass
class ConversationTurn:
    query: str
    answer: str
    turn_number: int


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class NotebookLMClient:
    """HTTP client for the NotebookLM internal API.

    Usage::

        with NotebookLMClient(cookies, csrf_token, session_id) as client:
            notebooks = client.list_notebooks()
    """

    def __init__(
        self,
        cookies: dict[str, str],
        csrf_token: str = "",
        session_id: str = "",
    ):
        self.cookies = cookies
        self.csrf_token = csrf_token
        self._session_id = session_id
        self._client: httpx.Client | None = None
        self._conversation_cache: dict[str, list[ConversationTurn]] = {}
        self._reqid_counter = random.randint(100000, 999999)

        # Auto-refresh CSRF token if not provided
        if not self.csrf_token:
            self._refresh_auth_tokens()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # HTTP client management
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            jar = httpx.Cookies()
            for name, value in self.cookies.items():
                jar.set(name, value, domain=".google.com")
                jar.set(name, value, domain=".googleusercontent.com")

            self._client = httpx.Client(
                cookies=jar,
                headers=config.DEFAULT_HEADERS,
                timeout=config.DEFAULT_TIMEOUT,
            )
        return self._client

    # ------------------------------------------------------------------
    # Auth token management
    # ------------------------------------------------------------------

    def _refresh_auth_tokens(self) -> None:
        """Fetch the NotebookLM homepage and extract CSRF + session ID."""
        jar = httpx.Cookies()
        for name, value in self.cookies.items():
            jar.set(name, value, domain=".google.com")

        with httpx.Client(
            cookies=jar,
            headers=config.PAGE_FETCH_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as tmp:
            resp = tmp.get(f"{config.BASE_URL}/")

            if "accounts.google.com" in str(resp.url):
                raise AuthenticationError(
                    "Cookies expired — redirected to Google login.",
                    hint="Run 'notebook-julian login' to re-authenticate.",
                )

            if resp.status_code != 200:
                raise AuthenticationError(
                    f"Failed to fetch NotebookLM page: HTTP {resp.status_code}"
                )

            html = resp.text
            csrf = extract_csrf_from_html(html)
            if not csrf:
                raise AuthenticationError(
                    "Could not extract CSRF token from page. "
                    "The page structure may have changed."
                )
            self.csrf_token = csrf

            sid = extract_session_id_from_html(html)
            if sid:
                self._session_id = sid

        # Persist refreshed tokens
        self._persist_tokens()

    def _persist_tokens(self) -> None:
        """Save current tokens back to disk (best-effort)."""
        try:
            save_tokens(
                AuthTokens(
                    cookies=self.cookies,
                    csrf_token=self.csrf_token,
                    session_id=self._session_id,
                    extracted_at=time.time(),
                )
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # RPC call with retry
    # ------------------------------------------------------------------

    def _call_rpc(
        self,
        rpc_id: str,
        params: Any,
        path: str = "/",
        timeout: float | None = None,
        *,
        _auth_retried: bool = False,
        _server_retry: int = 0,
    ) -> Any:
        """Execute an RPC call with automatic auth recovery and retry.

        Auth recovery: on 401/403 or RPC Error 16, refresh the CSRF token
        and retry once.

        Server errors: on 429/5xx, exponential backoff up to
        ``config.MAX_RETRIES`` attempts.
        """
        client = self._get_client()
        body = build_request_body(rpc_id, params, self.csrf_token)
        url = build_url(rpc_id, self._session_id, path)

        try:
            resp = client.post(url, content=body, timeout=timeout or config.DEFAULT_TIMEOUT)
            resp.raise_for_status()
            parsed = parse_response(resp.text)
            return extract_rpc_result(parsed, rpc_id)

        except httpx.HTTPStatusError as e:
            status = e.response.status_code

            # Retryable server errors (429, 5xx)
            if status in config.RETRYABLE_STATUS_CODES:
                if _server_retry < config.MAX_RETRIES:
                    delay = min(
                        config.RETRY_BASE_DELAY * (2**_server_retry),
                        config.RETRY_MAX_DELAY,
                    )
                    logger.warning(
                        "Server error %d (attempt %d/%d), retrying in %.1fs…",
                        status,
                        _server_retry + 1,
                        config.MAX_RETRIES + 1,
                        delay,
                    )
                    time.sleep(delay)
                    return self._call_rpc(
                        rpc_id, params, path, timeout,
                        _auth_retried=_auth_retried,
                        _server_retry=_server_retry + 1,
                    )
                raise APIError(f"Server error {status} after {config.MAX_RETRIES + 1} attempts")

            # Auth errors (401, 403)
            if status in (401, 403) and not _auth_retried:
                return self._retry_after_auth_refresh(rpc_id, params, path, timeout)
            raise APIError(f"HTTP {status}: {e}")

        except AuthExpiredError:
            if not _auth_retried:
                return self._retry_after_auth_refresh(rpc_id, params, path, timeout)
            raise AuthenticationError(
                "Authentication expired after retry.",
                hint="Run 'notebook-julian login' to re-authenticate.",
            )

    def _retry_after_auth_refresh(
        self,
        rpc_id: str,
        params: Any,
        path: str,
        timeout: float | None,
    ) -> Any:
        """Refresh CSRF token and retry the RPC call once."""
        try:
            self._refresh_auth_tokens()
        except AuthenticationError:
            # Try reloading from disk (user may have re-logged in externally)
            disk_tokens = load_tokens()
            if disk_tokens and disk_tokens.cookies:
                self.cookies = disk_tokens.cookies
                self.csrf_token = disk_tokens.csrf_token
                self._session_id = disk_tokens.session_id
            else:
                raise

        # Recreate HTTP client with fresh cookies/CSRF
        self._client = None
        return self._call_rpc(
            rpc_id, params, path, timeout,
            _auth_retried=True,
        )

    # ==================================================================
    # Domain methods — Notebooks
    # ==================================================================

    def list_notebooks(self) -> list[dict]:
        """List all notebooks.

        Returns:
            List of dicts with keys: ``id``, ``title``, ``source_count``,
            ``sources``, ``is_owned``, ``is_shared``, ``created_at``,
            ``modified_at``.
        """
        result = self._call_rpc(config.RPC_LIST_NOTEBOOKS, [None, 1, None, [2]])

        notebooks: list[dict] = []
        if not result or not isinstance(result, list):
            return notebooks

        notebook_list = result[0] if result and isinstance(result[0], list) else result

        for nb in notebook_list:
            if not isinstance(nb, list) or len(nb) < 3:
                continue

            title = nb[0] if isinstance(nb[0], str) else "Untitled"
            sources_data = nb[1] if len(nb) > 1 and isinstance(nb[1], list) else []
            notebook_id = nb[2] if len(nb) > 2 else None
            if not notebook_id:
                continue

            # Ownership & timestamps from metadata at position 5
            is_owned = True
            is_shared = False
            created_at = None
            modified_at = None

            if len(nb) > 5 and isinstance(nb[5], list) and len(nb[5]) > 0:
                meta = nb[5]
                is_owned = meta[0] == 1
                if len(meta) > 1:
                    is_shared = bool(meta[1])
                if len(meta) > 5:
                    modified_at = _parse_timestamp(meta[5])
                if len(meta) > 8:
                    created_at = _parse_timestamp(meta[8])

            # Extract source summaries
            sources = []
            for src in sources_data:
                if isinstance(src, list) and len(src) >= 2:
                    sid = src[0]
                    if isinstance(sid, list) and sid:
                        sid = sid[0]
                    sources.append({"id": sid, "title": src[1] if len(src) > 1 else "Untitled"})

            notebooks.append({
                "id": notebook_id,
                "title": title,
                "source_count": len(sources),
                "sources": sources,
                "is_owned": is_owned,
                "is_shared": is_shared,
                "created_at": created_at,
                "modified_at": modified_at,
            })

        return notebooks

    def get_notebook(self, notebook_id: str) -> Any:
        """Get raw notebook data (used internally by other methods)."""
        return self._call_rpc(
            config.RPC_GET_NOTEBOOK,
            [notebook_id, None, [2], None, 0],
            f"/notebook/{notebook_id}",
        )

    # ==================================================================
    # Domain methods — Sources
    # ==================================================================

    def list_sources(self, notebook_id: str) -> list[dict]:
        """List all sources in a notebook.

        Returns:
            List of dicts with keys: ``id``, ``title``, ``source_type``,
            ``source_type_name``, ``url``.
        """
        result = self.get_notebook(notebook_id)
        sources: list[dict] = []
        if not result or not isinstance(result, list) or len(result) < 1:
            return sources

        notebook_data = result[0] if isinstance(result[0], list) else result
        sources_data = notebook_data[1] if len(notebook_data) > 1 else []
        if not isinstance(sources_data, list):
            return sources

        for src in sources_data:
            if not isinstance(src, list) or len(src) < 3:
                continue

            source_id = src[0][0] if src[0] and isinstance(src[0], list) else None
            title = src[1] if len(src) > 1 else "Untitled"
            metadata = src[2] if len(src) > 2 and isinstance(src[2], list) else []

            source_type = None
            url = None
            if isinstance(metadata, list):
                if len(metadata) > 4:
                    source_type = metadata[4]
                if len(metadata) > 7 and isinstance(metadata[7], list) and metadata[7]:
                    url = metadata[7][0]

            sources.append({
                "id": source_id,
                "title": title,
                "source_type": source_type,
                "source_type_name": config.SOURCE_TYPES.get(source_type, "unknown"),
                "url": url,
            })

        return sources

    def get_source_content(self, source_id: str) -> dict:
        """Get the full text content of a source.

        Returns:
            Dict with keys: ``content``, ``title``, ``source_type``,
            ``url``, ``char_count``.
        """
        params = [[source_id], [2], [2]]
        result = self._call_rpc(config.RPC_GET_SOURCE, params)

        content = ""
        title = ""
        source_type = ""
        url = None

        if result and isinstance(result, list):
            # result[0] = [[source_id], title, metadata, ...]
            if len(result) > 0 and isinstance(result[0], list):
                meta_block = result[0]
                if len(meta_block) > 1 and isinstance(meta_block[1], str):
                    title = meta_block[1]
                if len(meta_block) > 2 and isinstance(meta_block[2], list):
                    metadata = meta_block[2]
                    if len(metadata) > 4:
                        type_code = metadata[4]
                        source_type = config.SOURCE_TYPES.get(type_code, "unknown")
                    if len(metadata) > 7 and isinstance(metadata[7], list) and metadata[7]:
                        url = metadata[7][0] if isinstance(metadata[7][0], str) else None

            # result[3][0] = content blocks
            if len(result) > 3 and isinstance(result[3], list):
                wrapper = result[3]
                if len(wrapper) > 0 and isinstance(wrapper[0], list):
                    text_parts: list[str] = []
                    for block in wrapper[0]:
                        if isinstance(block, list):
                            text_parts.extend(_extract_all_text(block))
                    content = "\n\n".join(text_parts)

        return {
            "content": content,
            "title": title,
            "source_type": source_type,
            "url": url,
            "char_count": len(content),
        }

    def add_url_source(self, notebook_id: str, url: str) -> dict | None:
        """Add a URL (web page or YouTube) as a source.

        Returns:
            Dict with ``id`` and ``title``, or ``None`` on failure.
        """
        is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()

        if is_youtube:
            source_data = [None, None, None, None, None, None, None, [url], None, None, 1]
        else:
            source_data = [None, None, [url], None, None, None, None, None, None, None, 1]

        params = [
            [source_data],
            notebook_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]

        try:
            result = self._call_rpc(
                config.RPC_ADD_SOURCE,
                params,
                f"/notebook/{notebook_id}",
                config.SOURCE_ADD_TIMEOUT,
            )
        except httpx.TimeoutException:
            return {"status": "timeout", "message": "Timed out but may have succeeded."}

        return _parse_source_result(result)

    def add_text_source(
        self, notebook_id: str, text: str, title: str = "Pasted Text"
    ) -> dict | None:
        """Add pasted text as a source.

        Returns:
            Dict with ``id`` and ``title``, or ``None`` on failure.
        """
        source_data = [None, [title, text], None, 2, None, None, None, None, None, None, 1]
        params = [
            [source_data],
            notebook_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]

        try:
            result = self._call_rpc(
                config.RPC_ADD_SOURCE,
                params,
                f"/notebook/{notebook_id}",
                config.SOURCE_ADD_TIMEOUT,
            )
        except httpx.TimeoutException:
            return {"status": "timeout", "message": "Timed out but may have succeeded."}

        return _parse_source_result(result, default_title=title)

    # ==================================================================
    # Domain methods — Query
    # ==================================================================

    def query(
        self,
        notebook_id: str,
        query_text: str,
        source_ids: list[str] | None = None,
        conversation_id: str | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Ask a question to the notebook AI.

        Supports follow-up queries by passing a ``conversation_id`` from
        a previous call.

        Returns:
            Dict with keys: ``answer``, ``conversation_id``,
            ``turn_number``, ``is_follow_up``.
        """
        client = self._get_client()

        # Get all source IDs if not specified
        if source_ids is None:
            nb_data = self.get_notebook(notebook_id)
            source_ids = _extract_source_ids(nb_data)

        is_new = conversation_id is None
        if is_new:
            conversation_id = str(uuid.uuid4())
            history = None
        else:
            history = self._build_conversation_history(conversation_id)

        sources_array = [[[sid]] for sid in source_ids] if source_ids else []

        params = [
            sources_array,
            query_text,
            history,
            [2, None, [1]],
            conversation_id,
        ]

        body = build_query_body(params, self.csrf_token)
        self._reqid_counter += 100000
        url = build_query_url(self._session_id, self._reqid_counter)

        resp = client.post(url, content=body, timeout=timeout or config.QUERY_TIMEOUT)
        resp.raise_for_status()

        answer = parse_query_response(resp.text)

        if answer:
            self._cache_turn(conversation_id, query_text, answer)

        turns = self._conversation_cache.get(conversation_id, [])
        return {
            "answer": answer,
            "conversation_id": conversation_id,
            "turn_number": len(turns),
            "is_follow_up": not is_new,
        }

    # ------------------------------------------------------------------
    # Conversation cache
    # ------------------------------------------------------------------

    def _build_conversation_history(self, conversation_id: str) -> list | None:
        turns = self._conversation_cache.get(conversation_id, [])
        if not turns:
            return None
        history = []
        for t in turns:
            history.append([t.answer, None, 2])
            history.append([t.query, None, 1])
        return history or None

    def _cache_turn(self, conversation_id: str, query: str, answer: str) -> None:
        if conversation_id not in self._conversation_cache:
            self._conversation_cache[conversation_id] = []
        n = len(self._conversation_cache[conversation_id]) + 1
        self._conversation_cache[conversation_id].append(
            ConversationTurn(query=query, answer=answer, turn_number=n)
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_source_result(result: Any, default_title: str = "Untitled") -> dict | None:
    """Extract source id and title from an add-source RPC response."""
    if result and isinstance(result, list) and len(result) > 0:
        source_list = result[0] if result else []
        if source_list and len(source_list) > 0:
            src = source_list[0]
            source_id = src[0][0] if src[0] else None
            title = src[1] if len(src) > 1 else default_title
            return {"id": source_id, "title": title}
    return None


def _extract_source_ids(notebook_data: Any) -> list[str]:
    """Extract source IDs from raw notebook data."""
    ids: list[str] = []
    if not notebook_data or not isinstance(notebook_data, list):
        return ids
    try:
        nb = notebook_data[0] if isinstance(notebook_data[0], list) else notebook_data
        sources = nb[1] if len(nb) > 1 and isinstance(nb[1], list) else []
        for src in sources:
            if isinstance(src, list) and src:
                wrapper = src[0]
                if isinstance(wrapper, list) and wrapper:
                    sid = wrapper[0]
                    if isinstance(sid, str):
                        ids.append(sid)
    except (IndexError, TypeError):
        pass
    return ids


def _extract_all_text(data: list) -> list[str]:
    """Recursively extract all non-empty strings from nested arrays."""
    texts: list[str] = []
    for item in data:
        if isinstance(item, str) and item:
            texts.append(item)
        elif isinstance(item, list):
            texts.extend(_extract_all_text(item))
    return texts


def _parse_timestamp(ts: Any) -> str | None:
    """Convert Google's [seconds, nanos] timestamp to ISO string."""
    if isinstance(ts, list) and len(ts) > 0 and isinstance(ts[0], (int, float)):
        from datetime import datetime, timezone

        return datetime.fromtimestamp(ts[0], tz=timezone.utc).isoformat()
    return None
