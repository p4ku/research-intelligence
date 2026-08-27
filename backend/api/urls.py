from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from .views.workspaces import WorkspaceViewSet
from .views.scrapers import ScraperViewSet
from .views.papers import PaperViewSet
from .views.extractions import ExtractionViewSet
from .views.hitl import HITLViewSet
from .views.chat import ChatViewSet
from .views.reports import ReportViewSet
from .views.agents import ResearchAgentViewSet
from .views.activity_logs import UserActivityLogViewSet
from .views.auth import LoginView, TokenRefreshView, UserProfileView
from .views.diagnostics import HealthCheckView, DeepDiagnosticsView

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'scrapers', ScraperViewSet, basename='scraper')
router.register(r'papers', PaperViewSet, basename='paper')
router.register(r'extractions', ExtractionViewSet, basename='extraction')
router.register(r'hitl', HITLViewSet, basename='hitl')
router.register(r'chat', ChatViewSet, basename='chat')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'agents', ResearchAgentViewSet, basename='agent')
router.register(r'activity-logs', UserActivityLogViewSet, basename='activity-log')

urlpatterns = [
    # OpenAPI 3.0 & Swagger UI
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-alias'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication & Diagnostics
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='refresh-token'),
    path('auth/me/', UserProfileView.as_view(), name='user-profile'),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('health/diagnostics/', DeepDiagnosticsView.as_view(), name='deep-diagnostics'),

    # REST ViewSets
    path('', include(router.urls)),
]
