import os
import sys
import importlib

# Ensure site-packages mcp/server path is included in __path__ for session, stdio, sse, fastmcp modules
site_pkgs = [p for p in sys.path if 'site-packages' in p]
for sp in site_pkgs:
    candidate = os.path.join(sp, 'mcp', 'server')
    if os.path.isdir(candidate) and candidate not in __path__:
        __path__.append(candidate)

# Re-export official MCP Server components
try:
    from .session import ServerSession
    from .stdio import stdio_server
except Exception:
    pass

def __getattr__(name):
    if name == 'app':
        return importlib.import_module('.app', __package__)
    _app = importlib.import_module('.app', __package__)
    return getattr(_app, name)
