"""Basic workflow: list notebooks, pick one, query it.

This script shows how the MCP tools work under the hood.
In practice, your AI assistant calls these automatically.

Prerequisites:
    pip install notebooklm-mcp-2026
    notebooklm-mcp-2026 login
"""

from __future__ import annotations

from notebooklm_mcp_2026.tools.auth_tools import check_auth
from notebooklm_mcp_2026.tools.notebooks import list_notebooks
from notebooklm_mcp_2026.tools.query import query_notebook
from notebooklm_mcp_2026.tools.sources import list_sources


def main():
    # 1. Verify authentication
    auth = check_auth()
    if auth["status"] != "authenticated":
        print(f"Not authenticated: {auth.get('message', '')}")
        print("Run: notebooklm-mcp-2026 login")
        return

    print(f"Authenticated ({auth['cookie_count']} cookies, {auth['age_hours']}h old)")

    # 2. List notebooks
    result = list_notebooks()
    if result["status"] != "success" or not result["notebooks"]:
        print("No notebooks found.")
        return

    for nb in result["notebooks"]:
        print(f"  [{nb['id'][:8]}...] {nb['title']} ({nb['source_count']} sources)")

    # 3. Pick the first notebook and list its sources
    notebook_id = result["notebooks"][0]["id"]
    sources = list_sources(notebook_id)
    if sources["status"] == "success":
        print(f"\nSources in '{result['notebooks'][0]['title']}':")
        for src in sources["sources"]:
            print(f"  - {src['title']} ({src['source_type_name']})")

    # 4. Ask a question
    answer = query_notebook(notebook_id, "What are the main topics covered?")
    if answer["status"] == "success":
        print(f"\nAI Answer:\n{answer['answer']}")
        print(f"\n(conversation_id: {answer['conversation_id']})")


if __name__ == "__main__":
    main()
