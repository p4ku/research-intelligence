from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChatSubmitView,
    ChatMessageDetailView,
    PaperChatSessionViewSet,
)

router = DefaultRouter()
router.register(r'sessions', PaperChatSessionViewSet, basename='chat-session')

urlpatterns = [
    path('', ChatSubmitView.as_view(), name='chat-submit'),
    path('messages/<uuid:message_id>/', ChatMessageDetailView.as_view(), name='chat-message-detail'),
    path('', include(router.urls)),
]
