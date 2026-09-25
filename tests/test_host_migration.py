"""Tests for the notebooklm.google.com -> notebook.google.com migration."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from notebooklm_mcp_2026 import config
from notebooklm_mcp_2026.auth import (
    SessionRejectedError,
    extract_build_label_from_html,
    extract_session_id_from_html,
    fetch_page_tokens,
    has_service_cookie,
    is_notebooklm_url,
    select_auth_cookies,
)
from notebooklm_mcp_2026.protocol import build_query_url, build_url

ACCOUNT = ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSIDTS", "SIDCC"]


def _cookie(name, domain, value=None):
    return {"name": name, "domain": domain, "value": value or f"{name}@{domain}"}


def _browser_dump():
    raw = [_cookie(n, ".google.com") for n in ACCOUNT]
    # Every Google service host gets its own OSID pair.
    for host in ("mail.google.com", "notebooklm.google.com", "notebook.google.com",
                 "drive.google.com", ".docs.google.com"):
        raw.append(_cookie("OSID", host))
        raw.append(_cookie("__Secure-OSID", host))
    raw.append(_cookie("NID", ".google.com"))  # not essential
    raw.append(_cookie("SID", "accounts.google.com", "wrong-host"))
    return raw


class TestDefaults:
    def test_base_url_is_new_host(self):
        assert config.BASE_URL == "https://notebook.google.com"
        assert config.NOTEBOOKLM_HOST == "notebook.google.com"
        assert config.BATCHEXECUTE_URL.startswith("https://notebook.google.com/")

    def test_legacy_host_recognised_but_not_used(self):
        assert is_notebooklm_url("https://notebooklm.google.com/notebook/x")
        assert is_notebooklm_url("https://notebook.google.com/")
        assert not is_notebooklm_url("https://accounts.google.com/ServiceLogin")
        assert not is_notebooklm_url("https://evil.example/notebook.google.com")


class TestSelectAuthCookies:
    def test_keeps_only_osid_for_current_host(self):
        cookies = select_auth_cookies(_browser_dump())
        assert cookies["OSID"] == "OSID@notebook.google.com"
        assert cookies["__Secure-OSID"] == "__Secure-OSID@notebook.google.com"

    def test_order_independent(self):
        cookies = select_auth_cookies(list(reversed(_browser_dump())))
        assert cookies["OSID"] == "OSID@notebook.google.com"

    def test_account_cookies_only_from_google_com(self):
        cookies = select_auth_cookies(_browser_dump())
        assert cookies["SID"] == "SID@.google.com"
        assert "NID" not in cookies
        assert set(ACCOUNT) <= cookies.keys()

    def test_missing_service_cookie_detected(self):
        raw = [c for c in _browser_dump() if c["domain"] != "notebook.google.com"]
        cookies = select_auth_cookies(raw)
        assert "OSID" not in cookies
        assert not has_service_cookie(cookies)


class TestHtmlExtraction:
    def test_negative_session_id(self):
        assert extract_session_id_from_html('"FdrFJe":"-4321987654321"') == "-4321987654321"

    def test_build_label(self):
        html = '..."cfb2h":"boq_labs-tailwind-frontend_20260923.16_p0",...'
        assert extract_build_label_from_html(html) == "boq_labs-tailwind-frontend_20260923.16_p0"
        assert extract_build_label_from_html("nothing") == ""

    def test_urls_use_live_build_label(self):
        assert "bl=live_bl" in build_url("wXbhsf", "1", "/", "live_bl")
        assert f"bl={config.BUILD_LABEL}" in build_url("wXbhsf")
        assert "bl=live_bl" in build_query_url("1", 5, "live_bl")


def _mock_transport(handler):
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    return patch("httpx.Client", side_effect=factory)


class TestFetchPageTokens:
    def test_success_extracts_tokens_and_rotated_cookies(self):
        def handler(request):
            assert request.url.host == "notebook.google.com"
            return httpx.Response(
                200,
                headers={"set-cookie": "SIDCC=rotated; Domain=.google.com; Path=/; Secure"},
                text='"SNlM0e":"csrf-1","FdrFJe":"-99","cfb2h":"bl-live"',
            )

        with _mock_transport(handler):
            page = fetch_page_tokens({"SID": "a", "SIDCC": "old"})
        assert page.csrf_token == "csrf-1"
        assert page.session_id == "-99"
        assert page.build_label == "bl-live"
        assert page.cookies["SIDCC"] == "rotated"
        assert page.cookies["SID"] == "a"

    def test_redirect_to_service_login_raises(self):
        def handler(request):
            if request.url.host == "notebook.google.com":
                return httpx.Response(
                    302,
                    headers={"location": "https://accounts.google.com/ServiceLogin?osid=1"},
                )
            return httpx.Response(200, text='"SNlM0e":"accounts-page-token"')

        with _mock_transport(handler), pytest.raises(SessionRejectedError, match="osid|ServiceLogin|accounts"):
            fetch_page_tokens({"SID": "a"})

    def test_client_maps_rejection_to_authentication_error(self):
        from notebooklm_mcp_2026.client import AuthenticationError, NotebookLMClient

        with patch(
            "notebooklm_mcp_2026.client.fetch_page_tokens",
            side_effect=SessionRejectedError("rejected"),
        ), pytest.raises(AuthenticationError):
            NotebookLMClient(cookies={"SID": "a"})


class TestExtractTokensFromBrowser:
    def test_reads_cookie_store_without_touching_tabs(self):
        from notebooklm_mcp_2026 import auth

        version = MagicMock()
        version.json.return_value = {"webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/x"}
        page = auth.PageTokens("csrf", "-1", "bl", {"SID": "a"})
        with patch("httpx.get", return_value=version) as get, \
             patch.object(auth, "execute_cdp_command",
                          return_value={"cookies": _browser_dump()}) as cdp, \
             patch.object(auth, "fetch_page_tokens", return_value=page) as fetch, \
             patch("httpx.put") as put:
            tokens = auth.extract_tokens_from_browser("http://127.0.0.1:9223/")
        get.assert_called_once()
        assert get.call_args.args[0] == "http://127.0.0.1:9223/json/version"
        cdp.assert_called_once_with("ws://127.0.0.1:9223/devtools/browser/x", "Storage.getCookies")
        put.assert_not_called()  # never opens a tab
        sent = fetch.call_args.args[0]
        assert sent["OSID"] == "OSID@notebook.google.com"
        assert tokens.csrf_token == "csrf" and tokens.build_label == "bl"

    def test_requires_notebook_host_session(self):
        from notebooklm_mcp_2026 import auth

        version = MagicMock()
        version.json.return_value = {"webSocketDebuggerUrl": "ws://x"}
        raw = [c for c in _browser_dump() if c["domain"] != "notebook.google.com"]
        with patch("httpx.get", return_value=version), \
             patch.object(auth, "execute_cdp_command", return_value={"cookies": raw}), \
             pytest.raises(RuntimeError, match="notebook.google.com"):
            auth.extract_tokens_from_browser("http://127.0.0.1:9223")
