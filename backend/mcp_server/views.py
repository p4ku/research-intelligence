import os
import asyncio
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from drf_spectacular.utils import extend_schema, OpenApiResponse
from mcp_server.server.app import mcp


class MCPInfoView(APIView):
    """
    Model Context Protocol (MCP) Server Discovery & Info Endpoint.
    Provides server capabilities, SSE transport URL, and catalog of registered tools.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['MCP Server & Tools'],
        summary="MCP Server Discovery & Capabilities",
        description="Returns MCP metadata, transport URLs, and tool registry summary.",
        responses={200: OpenApiResponse(description="MCP Server Info & Tools Catalog")}
    )
    def get(self, request):
        tools = []
        try:
            raw_tools = asyncio.run(mcp.list_tools())
            for t in raw_tools:
                tools.append({
                    "name": t.name,
                    "description": (t.description or "").strip().split('\n')[0],
                })
        except Exception:
            pass

        port = int(os.environ.get("PORT", 8001))
        host = request.get_host().split(':')[0]
        scheme = "https" if request.is_secure() else "http"

        return Response({
            "status": "online",
            "server_name": "schwarz-research-intelligence-mcp",
            "protocol_version": "2024-11-05",
            "transport": {
                "type": "sse",
                "endpoint": f"{scheme}://{host}:{port}/sse",
                "messages_endpoint": f"{scheme}://{host}:{port}/messages/"
            },
            "tools_count": len(tools),
            "tools": tools
        }, status=status.HTTP_200_OK)


class MCPHealthView(APIView):
    """
    FastMCP Server Health Check Endpoint.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['MCP Server & Tools'],
        summary="MCP Server Health Check",
        description="Health check for the FastMCP Model Context Protocol background daemon.",
        responses={200: OpenApiResponse(description="MCP Health Status")}
    )
    def get(self, request):
        try:
            tools_count = len(asyncio.run(mcp.list_tools()))
        except Exception:
            tools_count = 0

        return Response({
            "status": "healthy",
            "service": "mcp-server",
            "tools_registered": tools_count
        }, status=status.HTTP_200_OK)
