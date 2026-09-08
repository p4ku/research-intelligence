import uuid
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
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
    CRUD viewset for managing multi-turn PaperChatSessions.
    Scoped to session owner, workspace admins, managers, and staff.
    """
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'delete', 'patch', 'head', 'options']
    ordering_fields = ['created_at', 'updated_at', 'title', 'total_tokens', 'total_usd_cost']
    ordering = ['-updated_at']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PaperChatSessionDetailSerializer
        return PaperChatSessionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PaperChatSession.objects.none()

        from django.db.models import Count, Q

        base_qs = PaperChatSession.objects.select_related('workspace', 'paper', 'user').annotate(
            annotated_messages_count=Count('messages')
        )
        if self.action == 'retrieve':
            base_qs = base_qs.prefetch_related('messages')

        if user.is_staff or user.is_superuser:
            qs = base_qs.all()
        else:
            user_memberships = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', 'role'))
            admin_ws_ids = [ws_id for ws_id, role in user_memberships if role in ('admin', 'manager')]
            member_ws_ids = [ws_id for ws_id, _ in user_memberships]

            # Admins/managers see all sessions in their workspace; regular researchers see only their own sessions
            qs = base_qs.filter(
                Q(workspace_id__in=admin_ws_ids) |
                Q(workspace_id__in=member_ws_ids, user=user)
            )

        paper_id = self.request.query_params.get('paper_id')
        if paper_id:
            try:
                qs = qs.filter(paper_id=uuid.UUID(str(paper_id)))
            except (ValueError, TypeError):
                return qs.none()

        workspace_id = self.request.query_params.get('workspace_id')
        if workspace_id:
            try:
                qs = qs.filter(workspace_id=uuid.UUID(str(workspace_id)))
            except (ValueError, TypeError):
                return qs.none()

        return qs.order_by('-updated_at')

    def perform_update(self, serializer):
        session = self.get_object()
        user = self.request.user
        if not (user.is_staff or user.is_superuser or session.user_id == user.id):
            is_admin = WorkspaceMember.objects.filter(
                workspace=session.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not is_admin:
                raise PermissionDenied("You can only modify your own chat sessions.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or instance.user_id == user.id):
            is_admin = WorkspaceMember.objects.filter(
                workspace=instance.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not is_admin:
                raise PermissionDenied("You can only delete your own chat sessions.")
        instance.delete()
