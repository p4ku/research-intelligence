"""
Interactive academic paper & workspace Q&A MCP tool implementation.
Delegates to the ejected 'chat.mcp.tools' engine.
"""

def ask_paper_logic(*args, **kwargs):
    from chat.mcp.tools import ask_paper_logic as _logic
    return _logic(*args, **kwargs)

__all__ = [
    "ask_paper_logic",
]
