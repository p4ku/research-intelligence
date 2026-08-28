import uuid
from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema

from chat.models import PaperChatSession
from research_intelligence.models import WorkspaceMember
from chat.serializers import (
    PaperChatSessionSerializer,
    PaperChatSessionDetailSerializer,
)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class PaperChatSessionViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for managing multi-turn PaperChatSessions within accessible workspaces.
    """
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'delete', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PaperChatSessionDetailSerializer
        return PaperChatSessionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PaperChatSession.objects.none()

        from django.db.models import Count

        base_qs = PaperChatSession.objects.select_related('workspace', 'paper', 'user').annotate(
            annotated_messages_count=Count('messages')
        )
        if self.action == 'retrieve':
            base_qs = base_qs.prefetch_related('messages')

        if user.is_staff or user.is_superuser:
            qs = base_qs.all()
        else:
            accessible_ws = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=accessible_ws)

        paper_id = self.request.query_params.get('paper_id')
        if paper_id:
            try:
                qs = qs.filter(paper_id=uuid.UUID(paper_id))
            except ValueError:
                pass

        workspace_id = self.request.query_params.get('workspace_id')
        if workspace_id:
            try:
                qs = qs.filter(workspace_id=uuid.UUID(workspace_id))
            except ValueError:
                pass

        return qs.order_by('-updated_at')
