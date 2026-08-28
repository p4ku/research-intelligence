"""
Legacy backwards-compatibility wrapper for FastMCP Server.
All core MCP functionality has been ejected to the 'mcp' Django application.
"""
import sys
import os

from mcp.server import *
from mcp.server import create_app, mcp

if __name__ == "__main__":
    import uvicorn
    app = create_app()
    port = int(os.environ.get("PORT", 8001))
    print(f"Starting FastMCP SSE Server on port {port} (via legacy research_intelligence.mcp.server proxy)...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
