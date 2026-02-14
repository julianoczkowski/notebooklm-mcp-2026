"""Tests for the client module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_mcp_2026.client import (
    NotebookLMClient,
    _extract_all_text,
    _extract_source_ids,
    _parse_source_result,
    _parse_timestamp,
)


class TestParseTimestamp:
    def test_valid_timestamp(self):
        result = _parse_timestamp([1700000000, 0])
        assert result is not None
        assert "2023-11-14" in result

    def test_none_input(self):
        assert _parse_timestamp(None) is None

    def test_empty_list(self):
        assert _parse_timestamp([]) is None

    def test_non_numeric(self):
        assert _parse_timestamp(["not a number"]) is None


class TestExtractAllText:
    def test_flat_list(self):
        assert _extract_all_text(["hello", "world"]) == ["hello", "world"]

    def test_nested(self):
        assert _extract_all_text([["a", ["b"]], "c"]) == ["a", "b", "c"]

    def test_mixed(self):
        assert _extract_all_text([1, "text", None, [2, "more"]]) == ["text", "more"]

    def test_empty(self):
        assert _extract_all_text([]) == []

    def test_empty_strings_skipped(self):
        assert _extract_all_text(["", "x", ""]) == ["x"]


class TestExtractSourceIds:
    def test_normal_structure(self):
        data = [["Title", [[["src-1"], "S1"], [["src-2"], "S2"]], "nb-id"]]
        assert _extract_source_ids(data) == ["src-1", "src-2"]

    def test_empty(self):
        assert _extract_source_ids(None) == []
        assert _extract_source_ids([]) == []

    def test_no_sources(self):
        data = [["Title", [], "nb-id"]]
        assert _extract_source_ids(data) == []


class TestParseSourceResult:
    def test_normal(self):
        # Structure: result[0] = source_list, source_list[0] = source_data
        # source_data[0] = [source_id], source_data[1] = title
        result = [[[["src-id-1"], "Source Title"]]]
        parsed = _parse_source_result(result)
        assert parsed is not None
        assert parsed["id"] == "src-id-1"
        assert parsed["title"] == "Source Title"

    def test_none_result(self):
        assert _parse_source_result(None) is None

    def test_empty_list(self):
        assert _parse_source_result([]) is None


class TestNotebookLMClientListNotebooks:
    """Test list_notebooks parsing with mocked HTTP."""

    def _make_response(self, inner_data):
        """Build a mock batchexecute response."""
        from tests.conftest import _build_batchexecute_response

        inner_json = json.dumps(inner_data)
        chunk = json.dumps([["wrb.fr", "wXbhsf", inner_json, None, None, None, "generic"]])
        return _build_batchexecute_response(chunk)

    @patch.object(NotebookLMClient, "_refresh_auth_tokens")
    def test_parses_notebooks(self, mock_refresh, sample_cookies):
        mock_refresh.return_value = None

        client = NotebookLMClient(
            cookies=sample_cookies,
            csrf_token="fake-csrf",
            session_id="fake-sid",
        )

        # Mock the HTTP client
        inner_data = [
            [
                [
                    "Test Notebook",
                    [[["src-1"], "Source 1"]],
                    "nb-123",
                    None,
                    None,
                    [1, False, True, None, None, [1700000000, 0], None, None, [1699000000, 0]],
                ]
            ]
        ]
        response_text = self._make_response(inner_data)

        mock_resp = MagicMock()
        mock_resp.text = response_text
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post.return_value = mock_resp
        client._client = mock_http

        notebooks = client.list_notebooks()

        assert len(notebooks) == 1
        assert notebooks[0]["id"] == "nb-123"
        assert notebooks[0]["title"] == "Test Notebook"
        assert notebooks[0]["source_count"] == 1
        assert notebooks[0]["is_owned"] is True

        client.close()

    @patch.object(NotebookLMClient, "_refresh_auth_tokens")
    def test_empty_response(self, mock_refresh, sample_cookies):
        mock_refresh.return_value = None

        client = NotebookLMClient(
            cookies=sample_cookies,
            csrf_token="fake",
            session_id="123",
        )

        response_text = self._make_response([])
        mock_resp = MagicMock()
        mock_resp.text = response_text
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post.return_value = mock_resp
        client._client = mock_http

        notebooks = client.list_notebooks()
        assert notebooks == []
        client.close()
