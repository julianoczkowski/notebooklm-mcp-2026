"""MCP server for notebooklm-mcp-2026.

The server exposes 9 tools via the Model Context Protocol over stdio
transport. No running HTTP server is required — MCP clients launch
this as a subprocess.

CLI entry point lives in ``cli.py``. This module owns the FastMCP
instance and the global client singleton.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .client import NotebookLMClient

# ---------------------------------------------------------------------------
# Global client singleton
# ---------------------------------------------------------------------------

_client: NotebookLMClient | None = None


def get_client() -> NotebookLMClient:
    """Get or create the API client from cached tokens.

    Called by tool functions in the ``tools/`` subpackage.

    Raises:
        ValueError: If no saved credentials are found.
    """
    global _client
    if _client is None:
        from .auth import load_tokens

        tokens = load_tokens()
        if tokens is None:
            raise ValueError(
                "Not authenticated. Run 'notebooklm-mcp-2026 login' in your terminal first."
            )
        _client = NotebookLMClient(
            cookies=tokens.cookies,
            csrf_token=tokens.csrf_token,
            session_id=tokens.session_id,
        )
    return _client


def reset_client() -> None:
    """Close and reset the global client (useful after re-auth)."""
    global _client
    if _client:
        _client.close()
    _client = None


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="notebooklm-mcp-2026",
    instructions=(
        "NotebookLM MCP Server — query Google NotebookLM notebooks for context.\n\n"
        "If you get authentication errors, ask the user to run "
        "'notebooklm-mcp-2026 login' in their terminal.\n\n"
        "Typical workflow:\n"
        "1. list_notebooks — find the notebook ID\n"
        "2. list_sources — see what sources are in it\n"
        "3. query_notebook — ask a question\n"
        "4. get_source_content — read raw source text if needed"
    ),
)


def _register_tools() -> None:
    """Register all 9 tool functions with the MCP server."""
    from .tools import ALL_TOOLS

    for tool_fn in ALL_TOOLS:
        mcp.tool()(tool_fn)


_register_tools()
