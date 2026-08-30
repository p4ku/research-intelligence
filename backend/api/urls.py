from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def trigger_error(request):
    division_by_zero = 1 / 0


from .views.workspaces import WorkspaceViewSet
from .views.scrapers import ScraperViewSet
from .views.papers import PaperViewSet
from .views.extractions import ExtractionViewSet
from .views.hitl import HITLViewSet
from .views.chat import ChatSubmitView, ChatStreamView, ChatMessageDetailView, PaperChatSessionViewSet
from .views.reports import ReportViewSet
from .views.agents import ResearchAgentViewSet
from .views.pipeline_runs import PipelineRunViewSet, ComponentRunViewSet
from .views.activity_logs import UserActivityLogViewSet
from .views.auth import LoginView, TokenRefreshView, UserProfileView, ChangePasswordView
from .views.diagnostics import HealthCheckView, DeepDiagnosticsView

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'pipeline-runs', PipelineRunViewSet, basename='pipeline-run')
router.register(r'component-runs', ComponentRunViewSet, basename='component-run')
router.register(r'agents', ResearchAgentViewSet, basename='agent')
router.register(r'scrapers', ScraperViewSet, basename='scraper')
router.register(r'papers', PaperViewSet, basename='paper')
router.register(r'extractions', ExtractionViewSet, basename='extraction')
router.register(r'hitl', HITLViewSet, basename='hitl')
router.register(r'chat/sessions', PaperChatSessionViewSet, basename='chat-session')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'activity-logs', UserActivityLogViewSet, basename='activity-log')

urlpatterns = [
    re_path(r'^sentry-debug/?$', trigger_error, name='api-sentry-debug-inner'),

    # OpenAPI 3.0 & Swagger UI
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-alias'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication & User Profile Self-Management
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='refresh-token'),
    path('auth/me/', UserProfileView.as_view(), name='user-profile'),
    path('auth/me/password/', ChangePasswordView.as_view(), name='user-change-password-alias'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='user-change-password'),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('health/diagnostics/', DeepDiagnosticsView.as_view(), name='deep-diagnostics'),

    # Interactive Paper Chat & Knowledge Explorer
    path('chat/', ChatSubmitView.as_view(), name='chat-submit'),
    path('chat/stream/', ChatStreamView.as_view(), name='chat-stream'),
    path('chat/messages/<uuid:message_id>/', ChatMessageDetailView.as_view(), name='chat-message-detail'),

    # REST ViewSets
    path('', include(router.urls)),
]
