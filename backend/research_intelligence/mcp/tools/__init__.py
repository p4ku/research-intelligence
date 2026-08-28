"""
Legacy backwards-compatibility re-exports for MCP tool logic.
All tool logic is now hosted in the standalone 'mcp.tools' package.
"""
from mcp.tools import *
from mcp.tools import __all__ as _tools_all

__all__ = list(_tools_all)
