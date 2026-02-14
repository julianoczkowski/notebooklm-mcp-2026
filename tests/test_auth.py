"""Tests for the auth module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from notebooklm_mcp_2026.auth import (
    AuthTokens,
    extract_csrf_from_html,
    extract_session_id_from_html,
    load_tokens,
    save_tokens,
    validate_cookies,
)


class TestAuthTokens:
    def test_round_trip(self, sample_cookies, sample_csrf_token):
        tokens = AuthTokens(
            cookies=sample_cookies,
            csrf_token=sample_csrf_token,
            session_id="12345",
            extracted_at=1700000000.0,
        )
        data = tokens.to_dict()
        restored = AuthTokens.from_dict(data)
        assert restored.cookies == sample_cookies
        assert restored.csrf_token == sample_csrf_token
        assert restored.session_id == "12345"
        assert restored.extracted_at == 1700000000.0

    def test_from_dict_missing_fields(self):
        tokens = AuthTokens.from_dict({"cookies": {"SID": "x"}})
        assert tokens.cookies == {"SID": "x"}
        assert tokens.csrf_token == ""
        assert tokens.session_id == ""

    def test_from_dict_empty(self):
        tokens = AuthTokens.from_dict({})
        assert tokens.cookies == {}


class TestSaveLoadTokens:
    def test_save_and_load(self, sample_cookies, tmp_path):
        auth_file = tmp_path / "auth.json"
        tokens = AuthTokens(cookies=sample_cookies, csrf_token="csrf123")

        with patch("notebooklm_mcp_2026.auth.AUTH_FILE", auth_file), \
             patch("notebooklm_mcp_2026.auth.STORAGE_DIR", tmp_path):
            save_tokens(tokens)
            loaded = load_tokens()

        assert loaded is not None
        assert loaded.cookies == sample_cookies
        assert loaded.csrf_token == "csrf123"

    def test_file_permissions(self, sample_cookies, tmp_path):
        auth_file = tmp_path / "auth.json"
        tokens = AuthTokens(cookies=sample_cookies)

        with patch("notebooklm_mcp_2026.auth.AUTH_FILE", auth_file), \
             patch("notebooklm_mcp_2026.auth.STORAGE_DIR", tmp_path):
            save_tokens(tokens)

        if os.name != "nt":  # Skip on Windows
            mode = auth_file.stat().st_mode & 0o777
            assert mode == 0o600

    def test_load_missing_file(self, tmp_path):
        with patch("notebooklm_mcp_2026.auth.AUTH_FILE", tmp_path / "nonexistent.json"):
            assert load_tokens() is None

    def test_load_corrupt_file(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("not valid json{{{")
        with patch("notebooklm_mcp_2026.auth.AUTH_FILE", auth_file):
            assert load_tokens() is None

    def test_load_empty_cookies(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(json.dumps({"cookies": {}}))
        with patch("notebooklm_mcp_2026.auth.AUTH_FILE", auth_file):
            assert load_tokens() is None


class TestValidateCookies:
    def test_valid(self, sample_cookies):
        assert validate_cookies(sample_cookies) is True

    def test_missing_required(self):
        cookies = {"SID": "x", "HSID": "y"}  # Missing SSID, APISID, SAPISID
        assert validate_cookies(cookies) is False

    def test_empty(self):
        assert validate_cookies({}) is False


class TestExtractCsrf:
    def test_extracts_token(self):
        html = 'some stuff "SNlM0e":"AHBxJ9q_test_token" more stuff'
        assert extract_csrf_from_html(html) == "AHBxJ9q_test_token"

    def test_no_token(self):
        assert extract_csrf_from_html("<html>no token here</html>") == ""

    def test_empty_html(self):
        assert extract_csrf_from_html("") == ""


class TestExtractSessionId:
    def test_extracts_fdrfje(self):
        html = 'stuff "FdrFJe":"1234567890" more'
        assert extract_session_id_from_html(html) == "1234567890"

    def test_extracts_fsid_pattern(self):
        html = 'f.sid="9876543210"'
        assert extract_session_id_from_html(html) == "9876543210"

    def test_no_session_id(self):
        assert extract_session_id_from_html("<html>nothing</html>") == ""
