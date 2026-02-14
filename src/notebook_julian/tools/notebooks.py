"""Notebook tools — list_notebooks and get_notebook."""

from __future__ import annotations

from typing import Any


def list_notebooks(max_results: int = 50) -> dict[str, Any]:
    """List all NotebookLM notebooks.

    Returns a list of notebooks with their title, ID, source count,
    ownership info, and timestamps.

    Args:
        max_results: Maximum number of notebooks to return (default: 50).

    Returns:
        Status dict with ``notebooks`` list on success.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    try:
        client = get_client()
        notebooks = client.list_notebooks()
        return {
            "status": "success",
            "count": len(notebooks[:max_results]),
            "notebooks": notebooks[:max_results],
        }
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Unexpected error: {e}"}


def get_notebook(notebook_id: str) -> dict[str, Any]:
    """Get notebook details including its list of sources.

    Args:
        notebook_id: The notebook UUID (from ``list_notebooks``).

    Returns:
        Status dict with notebook metadata and sources list.
    """
    from ..server import get_client
    from ..client import AuthenticationError, NotebookJulianError

    if not notebook_id or not notebook_id.strip():
        return {"status": "error", "error": "notebook_id is required."}

    try:
        client = get_client()
        sources = client.list_sources(notebook_id)

        # Also find this notebook in the list to get its title
        notebooks = client.list_notebooks()
        nb_info = next((nb for nb in notebooks if nb["id"] == notebook_id), None)

        return {
            "status": "success",
            "notebook_id": notebook_id,
            "title": nb_info["title"] if nb_info else "Unknown",
            "source_count": len(sources),
            "sources": sources,
        }
    except AuthenticationError as e:
        return {"status": "error", "error": str(e), "hint": e.hint}
    except NotebookJulianError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Unexpected error: {e}"}
