"""Unit tests for the 9 MCP tool functions."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(**overrides):
    """Create a mock NotebookLMClient with sensible defaults."""
    client = MagicMock()
    client.list_notebooks.return_value = [
        {
            "id": "nb-1",
            "title": "My Notebook",
            "source_count": 1,
            "sources": [{"id": "src-1", "title": "Source One"}],
            "is_owned": True,
            "is_shared": False,
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-02T00:00:00+00:00",
        }
    ]
    client.list_sources.return_value = [
        {
            "id": "src-1",
            "title": "Source One",
            "source_type": 5,
            "source_type_name": "web_page",
            "url": "https://example.com",
        }
    ]
    client.get_source_content.return_value = {
        "content": "Hello world",
        "title": "Source One",
        "source_type": "web_page",
        "url": "https://example.com",
        "char_count": 11,
    }
    client.query.return_value = {
        "answer": "The answer is 42.",
        "conversation_id": "conv-1",
        "turn_number": 1,
        "is_follow_up": False,
    }
    client.add_url_source.return_value = {"id": "src-new", "title": "Added URL"}
    client.add_text_source.return_value = {"id": "src-new", "title": "Pasted Text"}
    for key, val in overrides.items():
        setattr(client, key, val)
    return client


def _mock_tokens():
    """Create a mock AuthTokens object."""
    tokens = MagicMock()
    tokens.cookies = {"SID": "fake"}
    tokens.csrf_token = "csrf"
    tokens.session_id = "sid"
    tokens.extracted_at = time.time()
    return tokens


# ---------------------------------------------------------------------------
# list_notebooks
# ---------------------------------------------------------------------------


class TestListNotebooks:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.notebooks import list_notebooks

        result = list_notebooks()
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["notebooks"][0]["title"] == "My Notebook"

    @patch("notebooklm_mcp_2026.server.get_client")
    def test_max_results(self, mock_get_client):
        client = _mock_client()
        client.list_notebooks.return_value = [
            {"id": f"nb-{i}", "title": f"NB {i}"} for i in range(10)
        ]
        mock_get_client.return_value = client
        from notebooklm_mcp_2026.tools.notebooks import list_notebooks

        result = list_notebooks(max_results=3)
        assert result["count"] == 3

    @patch("notebooklm_mcp_2026.server.get_client")
    def test_auth_error(self, mock_get_client):
        from notebooklm_mcp_2026.client import AuthenticationError

        mock_get_client.return_value = _mock_client()
        mock_get_client.return_value.list_notebooks.side_effect = AuthenticationError("expired")
        from notebooklm_mcp_2026.tools.notebooks import list_notebooks

        result = list_notebooks()
        assert result["status"] == "error"
        assert "hint" in result

    @patch("notebooklm_mcp_2026.server.get_client")
    def test_unexpected_error(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        mock_get_client.return_value.list_notebooks.side_effect = RuntimeError("boom")
        from notebooklm_mcp_2026.tools.notebooks import list_notebooks

        result = list_notebooks()
        assert result["status"] == "error"
        assert "hint" in result


# ---------------------------------------------------------------------------
# get_notebook
# ---------------------------------------------------------------------------


class TestGetNotebook:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.notebooks import get_notebook

        result = get_notebook("nb-1")
        assert result["status"] == "success"
        assert result["title"] == "My Notebook"
        assert result["source_count"] == 1

    def test_empty_notebook_id(self):
        from notebooklm_mcp_2026.tools.notebooks import get_notebook

        result = get_notebook("")
        assert result["status"] == "error"
        assert "required" in result["error"]


# ---------------------------------------------------------------------------
# list_sources
# ---------------------------------------------------------------------------


class TestListSources:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.sources import list_sources

        result = list_sources("nb-1")
        assert result["status"] == "success"
        assert result["count"] == 1

    def test_empty_notebook_id(self):
        from notebooklm_mcp_2026.tools.sources import list_sources

        result = list_sources("")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# get_source_content
# ---------------------------------------------------------------------------


class TestGetSourceContent:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.sources import get_source_content

        result = get_source_content("src-1")
        assert result["status"] == "success"
        assert result["content"] == "Hello world"
        assert result["char_count"] == 11

    def test_empty_source_id(self):
        from notebooklm_mcp_2026.tools.sources import get_source_content

        result = get_source_content("")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# query_notebook
# ---------------------------------------------------------------------------


class TestQueryNotebook:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.query import query_notebook

        result = query_notebook("nb-1", "What is the answer?")
        assert result["status"] == "success"
        assert result["answer"] == "The answer is 42."
        assert result["conversation_id"] == "conv-1"

    def test_empty_notebook_id(self):
        from notebooklm_mcp_2026.tools.query import query_notebook

        result = query_notebook("", "question")
        assert result["status"] == "error"

    def test_empty_query(self):
        from notebooklm_mcp_2026.tools.query import query_notebook

        result = query_notebook("nb-1", "")
        assert result["status"] == "error"

    @patch("notebooklm_mcp_2026.server.get_client")
    def test_with_conversation_id(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.query import query_notebook

        result = query_notebook("nb-1", "follow up", conversation_id="conv-1")
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# add_source_url
# ---------------------------------------------------------------------------


class TestAddSourceUrl:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.sources import add_source_url

        result = add_source_url("nb-1", "https://example.com")
        assert result["status"] == "success"
        assert result["id"] == "src-new"

    def test_empty_notebook_id(self):
        from notebooklm_mcp_2026.tools.sources import add_source_url

        result = add_source_url("", "https://example.com")
        assert result["status"] == "error"

    def test_invalid_url(self):
        from notebooklm_mcp_2026.tools.sources import add_source_url

        result = add_source_url("nb-1", "not-a-url")
        assert result["status"] == "error"
        assert "http" in result["error"]

    @patch("notebooklm_mcp_2026.server.get_client")
    def test_no_response(self, mock_get_client):
        client = _mock_client()
        client.add_url_source.return_value = None
        mock_get_client.return_value = client
        from notebooklm_mcp_2026.tools.sources import add_source_url

        result = add_source_url("nb-1", "https://example.com")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# add_source_text
# ---------------------------------------------------------------------------


class TestAddSourceText:
    @patch("notebooklm_mcp_2026.server.get_client")
    def test_success(self, mock_get_client):
        mock_get_client.return_value = _mock_client()
        from notebooklm_mcp_2026.tools.sources import add_source_text

        result = add_source_text("nb-1", "Some text content")
        assert result["status"] == "success"

    def test_empty_text(self):
        from notebooklm_mcp_2026.tools.sources import add_source_text

        result = add_source_text("nb-1", "")
        assert result["status"] == "error"

    def test_text_too_long(self):
        from notebooklm_mcp_2026.tools.sources import add_source_text

        result = add_source_text("nb-1", "x" * 500_001)
        assert result["status"] == "error"
        assert "500,000" in result["error"]


# ---------------------------------------------------------------------------
# check_auth
# ---------------------------------------------------------------------------


class TestCheckAuth:
    @patch("notebooklm_mcp_2026.auth.load_tokens")
    def test_not_authenticated(self, mock_load):
        mock_load.return_value = None
        from notebooklm_mcp_2026.tools.auth_tools import check_auth

        result = check_auth()
        assert result["status"] == "not_authenticated"

    @patch("notebooklm_mcp_2026.client.NotebookLMClient")
    @patch("notebooklm_mcp_2026.auth.load_tokens")
    def test_authenticated(self, mock_load, mock_client_cls):
        mock_load.return_value = _mock_tokens()
        mock_client_cls.return_value = MagicMock()

        from notebooklm_mcp_2026.tools.auth_tools import check_auth

        result = check_auth()
        assert result["status"] == "authenticated"
