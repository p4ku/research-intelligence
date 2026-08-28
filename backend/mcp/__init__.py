"""
FastMCP Modular Django Application for Schwarz Research Intelligence.
Exposes Model Context Protocol (MCP) Server, SSE endpoints, and AI tool capabilities.
"""
import os
import sys

default_app_config = 'mcp.apps.McpConfig'

# Ensure site-packages mcp path is included in __path__ for types, client, server, shared modules
site_pkgs = [p for p in sys.path if 'site-packages' in p]
for sp in site_pkgs:
    candidate = os.path.join(sp, 'mcp')
    if os.path.isdir(candidate) and candidate not in __path__:
        __path__.append(candidate)

# Make sure mcp.types and mcp.server are available
import mcp.types as types
globals()['types'] = types
sys.modules['mcp'].types = types

from mcp.types import *
from mcp.types import Role as SamplingRole

from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.client.session import ClientSession
from mcp.client.session_group import ClientSessionGroup
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import McpError, UrlElicitationRequiredError

def get_mcp_server():
    from .server import mcp
    return mcp

def create_app(*args, **kwargs):
    from .server import create_app as _create_app
    return _create_app(*args, **kwargs)
