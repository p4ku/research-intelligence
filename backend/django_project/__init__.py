import os
import sys

# Ensure local 'mcp' Django app directory is linked into 'mcp' namespace package
from . import mcp_namespace

from .celery import app as celery_app

__all__ = ('celery_app',)
