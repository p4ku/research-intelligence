from django.urls import path, re_path
from .views import PrometheusMetricsView, TelemetryAnalyticsAPIView

urlpatterns = [
    re_path(r'^metrics/?$', PrometheusMetricsView.as_view(), name='prometheus-metrics'),
    path('telemetry/', TelemetryAnalyticsAPIView.as_view(), name='telemetry-analytics'),
]
