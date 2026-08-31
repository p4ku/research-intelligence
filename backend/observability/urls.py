from django.urls import path
from .views import PrometheusMetricsView, TelemetryAnalyticsAPIView

urlpatterns = [
    path('metrics', PrometheusMetricsView.as_view(), name='prometheus-metrics-plain'),
    path('metrics/', PrometheusMetricsView.as_view(), name='prometheus-metrics'),
    path('telemetry/', TelemetryAnalyticsAPIView.as_view(), name='telemetry-analytics'),
]
