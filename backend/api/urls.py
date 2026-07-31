from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views.workspaces import WorkspaceViewSet
from .views.papers import PaperViewSet
from .views.extractions import ExtractionViewSet
from .views.hitl import HITLViewSet
from .views.chat import ChatViewSet
from .views.reports import ReportViewSet
from .views.agents import ResearchAgentViewSet
from .views.auth import LoginView, TokenRefreshView

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'papers', PaperViewSet, basename='paper')
router.register(r'extractions', ExtractionViewSet, basename='extraction')
router.register(r'hitl', HITLViewSet, basename='hitl')
router.register(r'chat', ChatViewSet, basename='chat')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'agents', ResearchAgentViewSet, basename='agent')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='refresh-token'),
    path('', include(router.urls)),
]
