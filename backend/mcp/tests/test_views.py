from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status


class MCPViewsTestCase(TestCase):
    """Test MCP Discovery and Health endpoints."""

    def setUp(self):
        self.client = APIClient()

    def test_mcp_info_endpoint(self):
        res = self.client.get('/mcp/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], 'online')
        self.assertEqual(data['server_name'], 'schwarz-research-intelligence-mcp')
        self.assertIn('transport', data)
        self.assertIn('tools_count', data)
        self.assertGreater(data['tools_count'], 0)

    def test_mcp_health_endpoint(self):
        res = self.client.get('/mcp/health/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], 'healthy')
        self.assertGreater(data['tools_registered'], 0)
