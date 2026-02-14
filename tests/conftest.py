"""Shared test fixtures."""

import json

import pytest

XSSI_PREFIX = ")]}'"


@pytest.fixture
def sample_cookies() -> dict[str, str]:
    """Minimal set of fake Google cookies for testing."""
    return {
        "SID": "fake-sid",
        "HSID": "fake-hsid",
        "SSID": "fake-ssid",
        "APISID": "fake-apisid",
        "SAPISID": "fake-sapisid",
        "__Secure-1PSID": "fake-1psid",
        "__Secure-3PSID": "fake-3psid",
    }


@pytest.fixture
def sample_csrf_token() -> str:
    return "AHBxJ9qFakeTokenXyz123"


def _build_batchexecute_response(*chunks: str) -> str:
    """Build a batchexecute response from JSON chunk strings."""
    lines = [XSSI_PREFIX]
    for chunk in chunks:
        lines.append(str(len(chunk.encode())))
        lines.append(chunk)
    return "\n".join(lines) + "\n"


@pytest.fixture
def sample_batchexecute_response() -> str:
    """A realistic batchexecute response for list_notebooks."""
    inner = json.dumps(
        [
            [
                [
                    "My Notebook",
                    [[["src-id-1"], "Source Title"]],
                    "nb-uuid-123",
                    None,
                    None,
                    [1, False, True, None, None, [1700000000, 0], None, None, [1699000000, 0]],
                ]
            ]
        ]
    )
    chunk = json.dumps([["wrb.fr", "wXbhsf", inner, None, None, None, "generic"]])
    return _build_batchexecute_response(chunk)


@pytest.fixture
def sample_query_response() -> str:
    """A realistic streaming query response."""
    # Type 2 = thinking (comes first)
    inner_thinking = json.dumps(
        [["Thinking about the question...", None, [], None, [2]]]
    )
    chunk_thinking = json.dumps(
        [["wrb.fr", None, inner_thinking, None, None, None, "generic"]]
    )

    # Type 1 = actual answer
    inner_answer = json.dumps(
        [
            [
                "This is the AI answer text that should be returned to the user.",
                None,
                [],
                None,
                [1],
            ]
        ]
    )
    chunk_answer = json.dumps(
        [["wrb.fr", None, inner_answer, None, None, None, "generic"]]
    )

    return _build_batchexecute_response(chunk_thinking, chunk_answer)
