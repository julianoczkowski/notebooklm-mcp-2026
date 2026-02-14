"""Google batchexecute RPC protocol — encoding and decoding.

This module contains **pure functions** with no I/O. Every function takes
data in and returns data out. This makes the protocol layer trivially
testable and keeps all network concerns in ``client.py``.

The batchexecute protocol is Google's internal RPC mechanism used by
NotebookLM (and many other Google products). It wraps JSON payloads in
a specific envelope format, URL-encodes them, and sends them as
``application/x-www-form-urlencoded`` POST bodies.

See ARCHITECTURE.md for detailed protocol documentation.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from .config import BATCHEXECUTE_URL, BASE_URL, BUILD_LABEL, QUERY_ENDPOINT


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuthExpiredError(Exception):
    """Raised when the server responds with RPC Error 16 (auth expired)."""


# ---------------------------------------------------------------------------
# batchexecute request building
# ---------------------------------------------------------------------------


def build_request_body(rpc_id: str, params: Any, csrf_token: str) -> str:
    """Encode an RPC call into a batchexecute POST body.

    The body looks like::

        f.req=<url-encoded JSON>&at=<csrf_token>&

    Args:
        rpc_id: The Google-internal RPC method identifier (e.g. ``"wXbhsf"``).
        params: The parameters for the RPC call (will be JSON-encoded).
        csrf_token: The ``SNlM0e`` CSRF token.

    Returns:
        The fully-encoded POST body as a string.
    """
    params_json = json.dumps(params, separators=(",", ":"))
    f_req = [[[rpc_id, params_json, None, "generic"]]]
    f_req_json = json.dumps(f_req, separators=(",", ":"))

    parts = [f"f.req={urllib.parse.quote(f_req_json, safe='')}"]
    if csrf_token:
        parts.append(f"at={urllib.parse.quote(csrf_token, safe='')}")
    return "&".join(parts) + "&"


def build_url(rpc_id: str, session_id: str = "", source_path: str = "/") -> str:
    """Build the batchexecute endpoint URL with query parameters.

    Args:
        rpc_id: The RPC method identifier.
        session_id: Optional ``FdrFJe`` session ID for affinity.
        source_path: The ``source-path`` parameter (defaults to ``"/"``).

    Returns:
        The full URL including query string.
    """
    params: dict[str, str] = {
        "rpcids": rpc_id,
        "source-path": source_path,
        "bl": BUILD_LABEL,
        "hl": "en",
        "rt": "c",
    }
    if session_id:
        params["f.sid"] = session_id
    return f"{BATCHEXECUTE_URL}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# batchexecute response parsing
# ---------------------------------------------------------------------------


def parse_response(response_text: str) -> list[Any]:
    """Parse a batchexecute response into a list of JSON chunks.

    The response format is::

        )]}'
        <byte_count>
        <json_array>
        <byte_count>
        <json_array>
        ...

    Args:
        response_text: Raw HTTP response body.

    Returns:
        A list of parsed JSON objects (one per chunk).
    """
    # Strip anti-XSSI prefix
    if response_text.startswith(")]}'"):
        response_text = response_text[4:]

    lines = response_text.strip().split("\n")
    results: list[Any] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Try to interpret as a byte-count line (precedes a JSON payload)
        try:
            int(line)  # byte count — consume and move to next line
            i += 1
            if i < len(lines):
                try:
                    results.append(json.loads(lines[i]))
                except json.JSONDecodeError:
                    pass
            i += 1
        except ValueError:
            # Not a byte count — try to parse directly as JSON
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                pass
            i += 1

    return results


def extract_rpc_result(parsed_response: list[Any], rpc_id: str) -> Any:
    """Extract the result payload for a specific RPC ID.

    Args:
        parsed_response: Output of :func:`parse_response`.
        rpc_id: The RPC method to look for.

    Returns:
        The JSON-decoded result, or ``None`` if not found.

    Raises:
        AuthExpiredError: If the response contains RPC Error 16.
    """
    for chunk in parsed_response:
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if not isinstance(item, list) or len(item) < 3:
                continue
            if item[0] != "wrb.fr" or item[1] != rpc_id:
                continue

            # Detect RPC Error 16 (auth expired):
            # ["wrb.fr", "RPC_ID", null, null, null, [16], "generic"]
            if (
                len(item) > 6
                and item[6] == "generic"
                and isinstance(item[5], list)
                and 16 in item[5]
            ):
                raise AuthExpiredError("RPC Error 16: authentication expired")

            result_str = item[2]
            if isinstance(result_str, str):
                try:
                    return json.loads(result_str)
                except json.JSONDecodeError:
                    return result_str
            return result_str

    return None


# ---------------------------------------------------------------------------
# Query (streaming) endpoint — different from batchexecute
# ---------------------------------------------------------------------------


def build_query_body(params: Any, csrf_token: str) -> str:
    """Build the POST body for the streaming query endpoint.

    The query endpoint uses a slightly different envelope: the outer wrapper
    is ``[None, <params_json>]`` instead of the triple-nested batchexecute
    format.
    """
    params_json = json.dumps(params, separators=(",", ":"))
    f_req = [None, params_json]
    f_req_json = json.dumps(f_req, separators=(",", ":"))

    parts = [f"f.req={urllib.parse.quote(f_req_json, safe='')}"]
    if csrf_token:
        parts.append(f"at={urllib.parse.quote(csrf_token, safe='')}")
    return "&".join(parts) + "&"


def build_query_url(session_id: str = "", reqid: int = 0) -> str:
    """Build the URL for the streaming query endpoint."""
    params: dict[str, str] = {
        "bl": BUILD_LABEL,
        "hl": "en",
        "_reqid": str(reqid),
        "rt": "c",
    }
    if session_id:
        params["f.sid"] = session_id
    return f"{BASE_URL}{QUERY_ENDPOINT}?{urllib.parse.urlencode(params)}"


def parse_query_response(response_text: str) -> str:
    """Parse a streaming query response and extract the final answer.

    The query endpoint returns multiple chunks. Each chunk may contain an
    answer (type 1) or a thinking step (type 2). We return the **longest**
    type-1 chunk, falling back to the longest type-2 chunk.

    Args:
        response_text: Raw HTTP response body.

    Returns:
        The extracted answer text, or ``""`` on parse failure.
    """
    if response_text.startswith(")]}'"):
        response_text = response_text[4:]

    lines = response_text.strip().split("\n")
    longest_answer = ""
    longest_thinking = ""

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        try:
            int(line)  # byte count
            i += 1
            if i < len(lines):
                text, is_answer = _extract_answer_from_chunk(lines[i])
                if text:
                    if is_answer and len(text) > len(longest_answer):
                        longest_answer = text
                    elif not is_answer and len(text) > len(longest_thinking):
                        longest_thinking = text
            i += 1
        except ValueError:
            text, is_answer = _extract_answer_from_chunk(line)
            if text:
                if is_answer and len(text) > len(longest_answer):
                    longest_answer = text
                elif not is_answer and len(text) > len(longest_thinking):
                    longest_thinking = text
            i += 1

    return longest_answer if longest_answer else longest_thinking


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_answer_from_chunk(json_str: str) -> tuple[str | None, bool]:
    """Extract answer text and type from a single JSON chunk.

    Returns:
        ``(text, is_answer)`` where *is_answer* is ``True`` for type-1
        chunks (actual answers) and ``False`` for type-2 (thinking).
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None, False

    if not isinstance(data, list) or len(data) == 0:
        return None, False

    for item in data:
        if not isinstance(item, list) or len(item) < 3:
            continue
        if item[0] != "wrb.fr":
            continue

        inner_json_str = item[2]
        if not isinstance(inner_json_str, str):
            continue

        try:
            inner_data = json.loads(inner_json_str)
        except json.JSONDecodeError:
            continue

        if not isinstance(inner_data, list) or len(inner_data) == 0:
            continue

        first_elem = inner_data[0]
        if isinstance(first_elem, list) and len(first_elem) > 0:
            answer_text = first_elem[0]
            if isinstance(answer_text, str) and len(answer_text) > 20:
                # Type indicator at first_elem[4][-1]: 1=answer, 2=thinking
                is_answer = False
                if len(first_elem) > 4 and isinstance(first_elem[4], list):
                    type_info = first_elem[4]
                    if len(type_info) > 0 and isinstance(type_info[-1], int):
                        is_answer = type_info[-1] == 1
                return answer_text, is_answer
        elif isinstance(first_elem, str) and len(first_elem) > 20:
            return first_elem, False

    return None, False
