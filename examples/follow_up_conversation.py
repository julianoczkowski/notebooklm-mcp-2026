"""Follow-up conversation: ask multiple questions in context.

Shows how to use conversation_id for multi-turn conversations
where each question builds on the previous answers.

Prerequisites:
    pip install notebooklm-mcp-2026
    notebooklm-mcp-2026 login
"""

from __future__ import annotations

from notebooklm_mcp_2026.tools.notebooks import list_notebooks
from notebooklm_mcp_2026.tools.query import query_notebook


def main():
    # Get the first notebook
    result = list_notebooks(max_results=1)
    if result["status"] != "success" or not result["notebooks"]:
        print("No notebooks found. Run: notebooklm-mcp-2026 login")
        return

    notebook_id = result["notebooks"][0]["id"]
    print(f"Using notebook: {result['notebooks'][0]['title']}\n")

    # First question — starts a new conversation
    r1 = query_notebook(notebook_id, "Summarize the key points in one paragraph.")
    if r1["status"] != "success":
        print(f"Error: {r1.get('error', '')}")
        return

    print(f"Q1: Summarize the key points in one paragraph.")
    print(f"A1: {r1['answer']}\n")

    # Follow-up — pass conversation_id to maintain context
    conversation_id = r1["conversation_id"]

    r2 = query_notebook(
        notebook_id,
        "Which of those points is most important and why?",
        conversation_id=conversation_id,
    )
    if r2["status"] == "success":
        print(f"Q2: Which of those points is most important and why?")
        print(f"A2: {r2['answer']}\n")
        print(f"(turn {r2['turn_number']}, follow-up: {r2['is_follow_up']})")


if __name__ == "__main__":
    main()
