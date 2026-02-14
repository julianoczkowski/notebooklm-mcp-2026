"""Integration tests — exercise tools through the FastMCP Client.

These tests use the in-process FastMCP Client to verify the full
MCP protocol roundtrip (JSON-RPC encoding, tool dispatch, response
formatting) without any real HTTP calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client


@pytest.fixture
def mock_notebook_client():
    """Mock get_client() so no real HTTP calls are made."""
    with patch("notebooklm_mcp_2026.server.get_client") as mock_get:
        client = MagicMock()
        client.list_notebooks.return_value = [
            {
                "id": "nb-test-123",
                "title": "Test Notebook",
                "source_count": 1,
                "sources": [{"id": "src-1", "title": "Test Source"}],
                "is_owned": True,
                "is_shared": False,
                "created_at": "2024-01-01T00:00:00+00:00",
                "modified_at": "2024-01-02T00:00:00+00:00",
            }
        ]
        client.list_sources.return_value = [
            {"id": "src-1", "title": "Test Source", "type": "web_page"}
        ]
        mock_get.return_value = client
        yield client


@pytest.mark.integration
async def test_tool_listing():
    """Verify all 9 tools are registered and discoverable."""
    from notebooklm_mcp_2026.server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "login",
            "check_auth",
            "list_notebooks",
            "get_notebook",
            "list_sources",
            "get_source_content",
            "query_notebook",
            "add_source_url",
            "add_source_text",
        }
        assert expected == tool_names


@pytest.mark.integration
async def test_list_notebooks_via_mcp(mock_notebook_client):
    """list_notebooks works through the MCP protocol."""
    from notebooklm_mcp_2026.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_notebooks", {"max_results": 10})
        # FastMCP 2.x returns CallToolResult; access .content for the list
        content = result.content
        assert len(content) > 0
        data = json.loads(content[0].text)
        assert data["status"] == "success"
        assert data["count"] == 1
        assert data["notebooks"][0]["title"] == "Test Notebook"


@pytest.mark.integration
async def test_check_auth_not_authenticated():
    """check_auth returns not_authenticated when no tokens on disk."""
    from notebooklm_mcp_2026.server import mcp

    # load_tokens is imported inside check_auth(), so we patch it at the source module
    with patch("notebooklm_mcp_2026.auth.load_tokens", return_value=None):
        async with Client(mcp) as client:
            result = await client.call_tool("check_auth", {})
            content = result.content
            assert len(content) > 0
            data = json.loads(content[0].text)
            assert data["status"] == "not_authenticated"
