"""MCP server and CLI entry point for notebooklm-mcp-2026.

The server exposes 9 tools via the Model Context Protocol over stdio
transport. No running HTTP server is required — MCP clients launch
this as a subprocess.

CLI usage::

    notebooklm-mcp-2026 serve   # Start MCP server (default)
    notebooklm-mcp-2026 login   # Interactive Chrome login
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from fastmcp import FastMCP

from . import __version__
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point (``notebooklm-mcp-2026`` command)."""
    parser = argparse.ArgumentParser(
        prog="notebooklm-mcp-2026",
        description="Secure MCP server for querying Google NotebookLM notebooks.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve (default)
    serve_parser = subparsers.add_parser("serve", help="Run the MCP server (stdio)")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # login
    login_parser = subparsers.add_parser(
        "login", help="Authenticate via Chrome (interactive)"
    )
    login_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for login (default: 300)",
    )

    # version
    subparsers.add_parser("version", help="Print version and exit")

    args = parser.parse_args()

    if args.command == "login":
        _handle_login(args.timeout)
    elif args.command == "version":
        print(f"notebooklm-mcp-2026 {__version__}")
    else:
        # Default to serve (even with no subcommand)
        debug = getattr(args, "debug", False)
        if debug:
            logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
        mcp.run(transport="stdio")


def _handle_login(timeout: int) -> None:
    """Interactive login flow — launches Chrome."""
    from .auth import extract_cookies_via_cdp, save_tokens

    print("Launching Chrome for NotebookLM login…")
    print("Log in to your Google account in the browser window.")
    print(f"Waiting up to {timeout} seconds…")
    print()

    try:
        tokens = extract_cookies_via_cdp(login_timeout=timeout)
        save_tokens(tokens)
        print()
        print(f"Authenticated successfully! Saved {len(tokens.cookies)} cookies.")
        if tokens.csrf_token:
            print("CSRF token: extracted")
        if tokens.session_id:
            print(f"Session ID: extracted")
        print()
        print("You can now use notebooklm-mcp-2026 as an MCP server.")
        print("Add it to your MCP client config:")
        print()
        print('  {"command": "notebooklm-mcp-2026", "args": ["serve"]}')
    except Exception as e:
        print(f"\nLogin failed: {e}", file=sys.stderr)
        sys.exit(1)
