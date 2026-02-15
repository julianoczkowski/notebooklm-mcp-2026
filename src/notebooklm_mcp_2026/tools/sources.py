"""Source tools — list, get content, add URL, add text."""

from __future__ import annotations

from typing import Any


def list_sources(notebook_id: str) -> dict[str, Any]:
    """List all sources in a notebook with titles and types.

    Args:
        notebook_id: The notebook UUID.

    Returns:
        Status dict with ``sources`` list (id, title, type, url).
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not notebook_id or not notebook_id.strip():
        return {"status": "error", "error": "notebook_id is required."}

    try:
        client = get_client()
        sources = client.list_sources(notebook_id)
        return {
            "status": "success",
            "notebook_id": notebook_id,
            "count": len(sources),
            "sources": sources,
        }
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "error": f"Unexpected error: {e}",
            "hint": "Run 'notebooklm-mcp-2026 doctor' to diagnose issues.",
        }


def get_source_content(source_id: str) -> dict[str, Any]:
    """Get the full text content of a specific source.

    Returns the raw indexed text from the source along with metadata
    (title, type, URL, character count).

    Args:
        source_id: The source UUID (from ``list_sources``).

    Returns:
        Status dict with ``content``, ``title``, ``source_type``,
        ``url``, ``char_count``.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not source_id or not source_id.strip():
        return {"status": "error", "error": "source_id is required."}

    try:
        client = get_client()
        result = client.get_source_content(source_id)
        return {"status": "success", **result}
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "error": f"Unexpected error: {e}",
            "hint": "Run 'notebooklm-mcp-2026 doctor' to diagnose issues.",
        }


def add_source_url(notebook_id: str, url: str) -> dict[str, Any]:
    """Add a URL (web page or YouTube video) as a source to a notebook.

    The URL will be fetched and indexed by NotebookLM. YouTube videos
    are automatically detected and handled appropriately.

    Args:
        notebook_id: The notebook UUID.
        url: The URL to add (must start with ``http://`` or ``https://``).

    Returns:
        Status dict with the new source ``id`` and ``title``.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not notebook_id or not notebook_id.strip():
        return {"status": "error", "error": "notebook_id is required."}
    if not url or not url.strip():
        return {"status": "error", "error": "url is required."}
    if not url.startswith(("http://", "https://")):
        return {"status": "error", "error": "url must start with http:// or https://"}

    try:
        client = get_client()
        result = client.add_url_source(notebook_id, url)
        if result is None:
            return {"status": "error", "error": "Failed to add source — no response."}
        return {"status": "success", **result}
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "error": f"Unexpected error: {e}",
            "hint": "Run 'notebooklm-mcp-2026 doctor' to diagnose issues.",
        }


def add_source_text(
    notebook_id: str,
    text: str,
    title: str = "Pasted Text",
) -> dict[str, Any]:
    """Add pasted text as a source to a notebook.

    The text will be indexed by NotebookLM and available for querying.

    Args:
        notebook_id: The notebook UUID.
        text: The text content to add.
        title: Display title for the source (default: ``"Pasted Text"``).

    Returns:
        Status dict with the new source ``id`` and ``title``.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not notebook_id or not notebook_id.strip():
        return {"status": "error", "error": "notebook_id is required."}
    if not text or not text.strip():
        return {"status": "error", "error": "text is required."}
    if len(text) > 500_000:
        return {"status": "error", "error": "text exceeds 500,000 character limit."}

    try:
        client = get_client()
        result = client.add_text_source(notebook_id, text, title)
        if result is None:
            return {"status": "error", "error": "Failed to add source — no response."}
        return {"status": "success", **result}
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "error": f"Unexpected error: {e}",
            "hint": "Run 'notebooklm-mcp-2026 doctor' to diagnose issues.",
        }
