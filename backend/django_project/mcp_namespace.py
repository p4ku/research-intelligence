"""
Namespace package linker for FastMCP Django Application.

Ensures that when Python imports `mcp` (which may exist in site-packages as the official FastMCP library),
the local Django application directory (`/app/mcp` or `backend/mcp`) and all its subpackages
(`server`, `tools`, `management`, `views`, `urls`, `admin`, `serializers`) are seamlessly merged
into the `mcp` namespace package.
"""
import os
import sys
import importlib

def setup_mcp_namespace():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_mcp = os.path.join(base_dir, 'mcp')
    if not os.path.isdir(local_mcp):
        return

    try:
        import mcp
        if local_mcp not in mcp.__path__:
            mcp.__path__.insert(0, local_mcp)

        # Merge all submodules that exist in the local mcp directory
        for item in os.listdir(local_mcp):
            item_path = os.path.join(local_mcp, item)
            if os.path.isdir(item_path) and not item.startswith(('_', '.')):
                submod_name = f"mcp.{item}"
                try:
                    submod = importlib.import_module(submod_name)
                    if hasattr(submod, '__path__') and item_path not in submod.__path__:
                        submod.__path__.insert(0, item_path)
                except Exception:
                    pass
    except Exception as e:
        pass

# Automatically execute upon import
setup_mcp_namespace()
