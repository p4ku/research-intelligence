"""
Lazy proxy for chat MCP tool logic from ejected chat application.
Eliminates module-level circular imports.
"""

def ask_paper_logic(*args, **kwargs):
    from chat.mcp.tools import ask_paper_logic as _logic
    return _logic(*args, **kwargs)

__all__ = [
    "ask_paper_logic",
]
