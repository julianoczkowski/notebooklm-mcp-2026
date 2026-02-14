"""MCP tool definitions for notebook-julian."""

from .auth_tools import check_auth, login
from .notebooks import get_notebook, list_notebooks
from .query import query_notebook
from .sources import add_source_text, add_source_url, get_source_content, list_sources

ALL_TOOLS = [
    login,
    check_auth,
    list_notebooks,
    get_notebook,
    list_sources,
    get_source_content,
    query_notebook,
    add_source_url,
    add_source_text,
]
