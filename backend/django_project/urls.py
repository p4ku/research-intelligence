from django.contrib import admin
from django.urls import path, re_path, include
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from api.views.diagnostics import HealthCheckView, DeepDiagnosticsView

urlpatterns = [
    # Legacy admin redirect from ResearchAgentProcess to PipelineRun
    path(
        'admin/research_intelligence/researchagentprocess/',
        RedirectView.as_view(pattern_name='admin:research_intelligence_pipelinerun_changelist', permanent=False),
    ),
    path(
        'admin/research_intelligence/researchagentprocess/<path:rest>',
        RedirectView.as_view(pattern_name='admin:research_intelligence_pipelinerun_changelist', permanent=False),
    ),
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

    # Enterprise Prometheus Metrics & Observability (/metrics)
    path('', include('observability.urls')),
]

