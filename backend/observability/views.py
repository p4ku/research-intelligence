from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .metrics import collect_telemetry_snapshot, generate_prometheus_metrics_text


class PrometheusMetricsView(APIView):
    """
    Prometheus / OpenTelemetry Metrics Exporter Endpoint.
    Exposes platform-wide operational telemetry in standard Prometheus text exposition format (v0.0.4).
    Targeted by Prometheus scrapers, Datadog agents, and Cloud Monitoring probes.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        metrics_text = generate_prometheus_metrics_text()
        return HttpResponse(
            metrics_text,
            content_type="text/plain; version=0.0.4; charset=utf-8"
        )


class TelemetryAnalyticsAPIView(APIView):
    """
    Structured JSON Telemetry & Operational Analytics Endpoint for Frontend Dashboards.
    Returns funnel conversion rates, cost per paper/run metrics, component latencies,
    and document cache savings.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Detailed system-wide telemetry and cost analytics snapshot"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=['Health & Diagnostics']
    )
    def get(self, request, *args, **kwargs):
        snapshot = collect_telemetry_snapshot()
        return Response(snapshot, status=status.HTTP_200_OK)
