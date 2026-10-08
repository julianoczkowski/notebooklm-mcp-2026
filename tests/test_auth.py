"""Tests for the auth module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_mcp_2026 import auth
from notebooklm_mcp_2026.auth import (
    AuthTokens,
    extract_csrf_from_html,
    extract_session_id_from_html,
    load_tokens,
    save_tokens,
    select_essential_cookies,
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

    def test_extracts_negative_fdrfje(self):
        html = '],"FdrFJe":"-7509409142960343516","GvXfVb":"5347362"'
        assert extract_session_id_from_html(html) == "-7509409142960343516"

    def test_extracts_negative_fsid_pattern(self):
        html = 'f.sid="-9876543210"'
        assert extract_session_id_from_html(html) == "-9876543210"

    def test_no_session_id(self):
        assert extract_session_id_from_html("<html>nothing</html>") == ""


class TestSelectEssentialCookies:
    def test_keeps_domain_wide_cookies(self):
        raw = [
            {"name": "SID", "domain": ".google.com", "value": "sid"},
            {"name": "SAPISID", "domain": ".google.com", "value": "sapisid"},
        ]
        assert select_essential_cookies(raw) == {"SID": "sid", "SAPISID": "sapisid"}

    def test_drops_non_essential_cookies(self):
        raw = [{"name": "NID", "domain": ".google.com", "value": "nid"}]
        assert select_essential_cookies(raw) == {}

    def test_host_only_cookie_for_notebooklm_host_wins(self):
        # Order matters for the old by-name logic: the last OSID seen won.
        raw = [
            {"name": "OSID", "domain": "notebook.google.com", "value": "right"},
            {"name": "OSID", "domain": "notebooklm.google.com", "value": "old-host"},
            {"name": "OSID", "domain": "accounts.google.com", "value": "accounts"},
        ]
        assert select_essential_cookies(raw) == {"OSID": "right"}

    def test_host_cookie_beats_domain_wide_in_either_order(self):
        host = {"name": "SIDCC", "domain": "notebook.google.com", "value": "host"}
        wide = {"name": "SIDCC", "domain": ".google.com", "value": "wide"}
        assert select_essential_cookies([host, wide]) == {"SIDCC": "host"}
        assert select_essential_cookies([wide, host]) == {"SIDCC": "host"}

    def test_other_host_only_cookies_are_ignored(self):
        raw = [{"name": "OSID", "domain": "notebooklm.google.com", "value": "old-host"}]
        assert select_essential_cookies(raw) == {}

    def test_custom_host(self):
        raw = [{"name": "OSID", "domain": "example.google.com", "value": "x"}]
        assert select_essential_cookies(raw, host="example.google.com") == {"OSID": "x"}


class TestLaunchChrome:
    """Cover the Windows multi-process launcher behavior in _launch_chrome."""

    def _patches(self, popen_mock):
        return [
            patch("notebooklm_mcp_2026.auth.subprocess.Popen", return_value=popen_mock),
            patch("notebooklm_mcp_2026.auth.time.sleep"),
            patch("notebooklm_mcp_2026.auth._remove_stale_locks"),
            patch("notebooklm_mcp_2026.auth.CHROME_PROFILE_DIR", MagicMock()),
        ]

    def _enter(self, patches):
        for p in patches:
            p.start()

    def _exit(self, patches):
        for p in patches:
            p.stop()

    def test_windows_multi_process_exit_with_live_cdp_succeeds(self):
        process = MagicMock()
        process.poll.return_value = 0  # launcher exited cleanly
        patches = self._patches(process)
        self._enter(patches)
        try:
            with patch(
                "notebooklm_mcp_2026.auth._get_debugger_ws_url",
                return_value="ws://localhost:9222/devtools/browser/abc",
            ):
                result = auth._launch_chrome(9222, chrome_path="/fake/chrome")
            assert result is process
        finally:
            self._exit(patches)

    def test_exit_with_no_cdp_raises(self):
        process = MagicMock()
        process.poll.return_value = 0
        process.stderr.read.return_value = b""
        patches = self._patches(process)
        self._enter(patches)
        try:
            with patch("notebooklm_mcp_2026.auth._get_debugger_ws_url", return_value=None):
                with pytest.raises(RuntimeError, match="Chrome exited immediately"):
                    auth._launch_chrome(9222, chrome_path="/fake/chrome")
        finally:
            self._exit(patches)

    def test_nonzero_exit_raises_even_if_cdp_responds(self):
        process = MagicMock()
        process.poll.return_value = 1  # real failure
        process.stderr.read.return_value = b"profile in use"
        patches = self._patches(process)
        self._enter(patches)
        try:
            with patch(
                "notebooklm_mcp_2026.auth._get_debugger_ws_url",
                return_value="ws://localhost:9222/devtools/browser/abc",
            ):
                with pytest.raises(RuntimeError, match="Chrome exited immediately"):
                    auth._launch_chrome(9222, chrome_path="/fake/chrome")
        finally:
            self._exit(patches)

    def test_running_process_returned(self):
        process = MagicMock()
        process.poll.return_value = None  # still running
        patches = self._patches(process)
        self._enter(patches)
        try:
            result = auth._launch_chrome(9222, chrome_path="/fake/chrome")
            assert result is process
        finally:
            self._exit(patches)


class TestHeadlessRefresh:
    def test_launch_args_headless_flag(self):
        assert "--headless=new" in auth._get_chrome_launch_args(9222, headless=True)
        assert "--headless=new" not in auth._get_chrome_launch_args(9222)

    def _profile(self, tmp_path):
        profile = tmp_path / "chrome-profile"
        profile.mkdir()
        return patch("notebooklm_mcp_2026.auth.CHROME_PROFILE_DIR", profile)

    def test_success_saves_and_returns_tokens(self, sample_cookies, tmp_path):
        tokens = AuthTokens(cookies=sample_cookies, csrf_token="csrf", session_id="-1")
        with (
            self._profile(tmp_path),
            patch("notebooklm_mcp_2026.auth.get_chrome_path", return_value="/fake/chrome"),
            patch("notebooklm_mcp_2026.auth.extract_cookies_via_cdp", return_value=tokens) as extract,
            patch("notebooklm_mcp_2026.auth.save_tokens") as save,
        ):
            assert auth.refresh_tokens_headless(timeout=5) is tokens
        extract.assert_called_once_with(login_timeout=5, headless=True)
        save.assert_called_once_with(tokens)

    def test_no_profile(self, tmp_path):
        with (
            patch("notebooklm_mcp_2026.auth.CHROME_PROFILE_DIR", tmp_path / "missing"),
            patch("notebooklm_mcp_2026.auth.extract_cookies_via_cdp") as extract,
        ):
            assert auth.refresh_tokens_headless() is None
        extract.assert_not_called()

    def test_no_chrome(self, tmp_path):
        with (
            self._profile(tmp_path),
            patch("notebooklm_mcp_2026.auth.get_chrome_path", return_value=None),
            patch("notebooklm_mcp_2026.auth.extract_cookies_via_cdp") as extract,
        ):
            assert auth.refresh_tokens_headless() is None
        extract.assert_not_called()

    def test_extraction_error_returns_none(self, tmp_path):
        with (
            self._profile(tmp_path),
            patch("notebooklm_mcp_2026.auth.get_chrome_path", return_value="/fake/chrome"),
            patch(
                "notebooklm_mcp_2026.auth.extract_cookies_via_cdp",
                side_effect=RuntimeError("Login timed out"),
            ),
            patch("notebooklm_mcp_2026.auth.save_tokens") as save,
        ):
            assert auth.refresh_tokens_headless() is None
        save.assert_not_called()

    def test_signed_out_profile_returns_none(self, sample_cookies, tmp_path):
        # A signed-out page has no SNlM0e, so no CSRF token is extracted.
        tokens = AuthTokens(cookies=sample_cookies, csrf_token="", session_id="")
        with (
            self._profile(tmp_path),
            patch("notebooklm_mcp_2026.auth.get_chrome_path", return_value="/fake/chrome"),
            patch("notebooklm_mcp_2026.auth.extract_cookies_via_cdp", return_value=tokens),
            patch("notebooklm_mcp_2026.auth.save_tokens") as save,
        ):
            assert auth.refresh_tokens_headless() is None
        save.assert_not_called()
