"""
FastMCP Server implementation and tool wrapper bindings.
"""
import pkgutil
import importlib

# Standard PEP-382/PEP-420 namespace extension
__path__ = pkgutil.extend_path(__path__, __name__)

# Standard PEP-562 lazy attribute delegation
def __getattr__(name):
    app_module = importlib.import_module('.app', __package__)
    return getattr(app_module, name)
