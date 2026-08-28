"""
FastMCP Modular Django Application for Schwarz Research Intelligence.
Exposes Model Context Protocol (MCP) Server, SSE endpoints, and AI tool capabilities.
"""
import pkgutil

# Standard Python namespace extension to merge local app with official mcp library
__path__ = pkgutil.extend_path(__path__, __name__)

# Re-export official MCP types, exceptions & sessions for library compatibility
try:
    from mcp.types import *  # noqa: F403
    from mcp.shared.exceptions import McpError, UrlElicitationRequiredError  # noqa: F401
    from mcp.server.session import ServerSession  # noqa: F401
    from mcp.server.stdio import stdio_server  # noqa: F401
    from mcp.client.session import ClientSession  # noqa: F401
except ImportError:
    pass
