"""Query tool — ask questions to a notebook's AI."""

from __future__ import annotations

from typing import Any


def query_notebook(
    notebook_id: str,
    query: str,
    source_ids: list[str] | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Ask a question to a notebook's AI about its sources.

    The AI will answer based on the content of the notebook's sources.
    For follow-up questions in the same conversation, pass the
    ``conversation_id`` from the previous response.

    Args:
        notebook_id: The notebook UUID.
        query: The question to ask.
        source_ids: Optional list of specific source IDs to query.
            If not provided, all sources in the notebook are used.
        conversation_id: For follow-up questions — pass the ID from
            a previous ``query_notebook`` response.

    Returns:
        Status dict with ``answer``, ``conversation_id``,
        ``turn_number``, and ``is_follow_up``.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not notebook_id or not notebook_id.strip():
        return {"status": "error", "error": "notebook_id is required."}
    if not query or not query.strip():
        return {"status": "error", "error": "query is required."}

    try:
        client = get_client()
        result = client.query(
            notebook_id=notebook_id,
            query_text=query,
            source_ids=source_ids,
            conversation_id=conversation_id,
        )
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
