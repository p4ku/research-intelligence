from django.contrib import admin
from django.urls import path, re_path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from api.views.diagnostics import HealthCheckView, DeepDiagnosticsView


def trigger_error(request):
    division_by_zero = 1 / 0


urlpatterns = [
    re_path(r'^sentry-debug/?$', trigger_error, name='sentry-debug'),
    re_path(r'^api/sentry-debug/?$', trigger_error, name='api-sentry-debug'),
    path('admin/', admin.site.urls),

    # OpenAPI 3.0 & Swagger UI routes
    path('schema/', SpectacularAPIView.as_view(), name='root-schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='root-swagger-ui'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='root-swagger-alias'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='root-redoc'),

    # Health & Diagnostics
    re_path(r'^api/health/?$', HealthCheckView.as_view(), name='api-health'),
    re_path(r'^api/health/diagnostics/?$', DeepDiagnosticsView.as_view(), name='api-deep-diagnostics'),
    re_path(r'^health/?$', HealthCheckView.as_view(), name='root-health'),
    re_path(r'^health/diagnostics/?$', DeepDiagnosticsView.as_view(), name='root-deep-diagnostics'),

    # API Routes (/api/...)
    path('api/', include('api.urls')),

    # MCP Server Discovery & Capabilities (/mcp/...)
    path('mcp/', include('mcp_server.urls')),
]

