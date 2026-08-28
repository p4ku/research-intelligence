"""
FastMCP Server implementation and tool wrapper bindings.
"""
import importlib

def __getattr__(name):
    app_module = importlib.import_module('.app', __package__)
    return getattr(app_module, name)
