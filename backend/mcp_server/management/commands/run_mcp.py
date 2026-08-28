import os
import uvicorn
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the Schwarz Research Intelligence FastMCP Server (SSE / JSON-RPC over HTTP)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=int(os.environ.get('PORT', 8001)),
            help='Port to run FastMCP Server on (default: 8001)'
        )
        parser.add_argument(
            '--host',
            type=str,
            default=os.environ.get('HOST', '0.0.0.0'),
            help='Host to bind FastMCP Server to (default: 0.0.0.0)'
        )
        parser.add_argument(
            '--reload',
            action='store_true',
            help='Enable auto-reload for development'
        )

    def handle(self, *args, **options):
        port = options['port']
        host = options['host']
        reload = options['reload']
        self.stdout.write(
            self.style.SUCCESS(f"🚀 Starting Schwarz Research Intelligence FastMCP Server on {host}:{port}...")
        )
        uvicorn.run(
            "mcp_server.server.app:app",
            host=host,
            port=port,
            reload=reload
        )
