"""Tests for the protocol module (pure functions)."""

import json
import urllib.parse

import pytest

from notebook_julian.protocol import (
    AuthExpiredError,
    build_query_body,
    build_query_url,
    build_request_body,
    build_url,
    extract_rpc_result,
    parse_query_response,
    parse_response,
)


class TestBuildRequestBody:
    def test_basic_structure(self):
        body = build_request_body("wXbhsf", [None, 1], "csrf123")
        assert body.startswith("f.req=")
        assert "at=csrf123" in body
        assert body.endswith("&")

    def test_params_are_json_encoded(self):
        body = build_request_body("wXbhsf", [None, 1, None, [2]], "tok")
        # URL-decode the f.req value
        parts = body.split("&")
        freq_part = parts[0].split("=", 1)[1]
        decoded = urllib.parse.unquote(freq_part)
        outer = json.loads(decoded)
        # Structure: [[[rpc_id, params_json, None, "generic"]]]
        assert len(outer) == 1
        assert len(outer[0]) == 1
        assert outer[0][0][0] == "wXbhsf"
        inner_params = json.loads(outer[0][0][1])
        assert inner_params == [None, 1, None, [2]]
        assert outer[0][0][2] is None
        assert outer[0][0][3] == "generic"

    def test_empty_csrf_token(self):
        body = build_request_body("abc", [1], "")
        assert "at=" not in body

    def test_csrf_special_chars_encoded(self):
        body = build_request_body("abc", [1], "tok/en+val=ue")
        # The CSRF token should be URL-encoded
        assert "tok%2Fen%2Bval%3Due" in body


class TestBuildUrl:
    def test_contains_rpc_id(self):
        url = build_url("wXbhsf")
        assert "rpcids=wXbhsf" in url

    def test_contains_build_label(self):
        url = build_url("wXbhsf")
        assert "bl=" in url

    def test_session_id_included(self):
        url = build_url("wXbhsf", session_id="12345")
        assert "f.sid=12345" in url

    def test_no_session_id(self):
        url = build_url("wXbhsf")
        assert "f.sid" not in url

    def test_source_path(self):
        url = build_url("rLM1Ne", source_path="/notebook/abc")
        assert "source-path=%2Fnotebook%2Fabc" in url


class TestParseResponse:
    def test_basic_response(self, sample_batchexecute_response):
        chunks = parse_response(sample_batchexecute_response)
        assert len(chunks) >= 1

    def test_strips_xssi_prefix(self):
        resp = ")]}'\n5\n[1,2]\n"
        chunks = parse_response(resp)
        assert [1, 2] in chunks

    def test_empty_response(self):
        assert parse_response("") == []

    def test_only_prefix(self):
        assert parse_response(")]}'") == []

    def test_multi_chunk(self):
        resp = ")]}'\n3\n[1]\n3\n[2]\n"
        chunks = parse_response(resp)
        assert [1] in chunks
        assert [2] in chunks


class TestExtractRpcResult:
    def test_extracts_matching_rpc(self, sample_batchexecute_response):
        chunks = parse_response(sample_batchexecute_response)
        result = extract_rpc_result(chunks, "wXbhsf")
        assert result is not None
        assert isinstance(result, list)

    def test_returns_none_for_missing_rpc(self, sample_batchexecute_response):
        chunks = parse_response(sample_batchexecute_response)
        result = extract_rpc_result(chunks, "NONEXISTENT")
        assert result is None

    def test_raises_on_error_16(self):
        error_chunk = [
            ["wrb.fr", "wXbhsf", None, None, None, [16], "generic"]
        ]
        with pytest.raises(AuthExpiredError):
            extract_rpc_result([error_chunk], "wXbhsf")

    def test_empty_parsed(self):
        assert extract_rpc_result([], "wXbhsf") is None

    def test_non_list_chunks_ignored(self):
        assert extract_rpc_result(["not a list", 42], "wXbhsf") is None


class TestBuildQueryBody:
    def test_structure(self):
        body = build_query_body([[], "question", None, [2, None, [1]], "conv-id"], "csrf")
        assert "f.req=" in body
        assert "at=csrf" in body

    def test_no_csrf(self):
        body = build_query_body([1], "")
        assert "at=" not in body


class TestBuildQueryUrl:
    def test_contains_reqid(self):
        url = build_query_url(reqid=200000)
        assert "_reqid=200000" in url

    def test_session_id(self):
        url = build_query_url(session_id="99999")
        assert "f.sid=99999" in url


class TestParseQueryResponse:
    def test_prefers_answer_over_thinking(self, sample_query_response):
        answer = parse_query_response(sample_query_response)
        assert "AI answer" in answer

    def test_empty_response(self):
        assert parse_query_response("") == ""

    def test_only_prefix(self):
        assert parse_query_response(")]}'") == ""

    def test_falls_back_to_thinking(self):
        """When no type-1 chunks, should fall back to type-2."""
        from tests.conftest import _build_batchexecute_response

        inner = json.dumps(
            [["This is a long thinking text that is definitely over twenty chars.", None, [], None, [2]]]
        )
        chunk = json.dumps([["wrb.fr", None, inner, None, None, None, "generic"]])
        resp = _build_batchexecute_response(chunk)
        result = parse_query_response(resp)
        assert "thinking text" in result
