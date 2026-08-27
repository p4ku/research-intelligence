from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema
from research_intelligence.models import Workspace, WorkspaceMember
from ..serializers.workspaces import WorkspaceSerializer


@extend_schema(tags=['Workspaces Management'])
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace (Projects) and prompt limits configurations.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return Workspace.objects.all().order_by('-created_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return Workspace.objects.filter(id__in=user_ws_ids).order_by('-created_at')

    def perform_create(self, serializer):
        workspace = serializer.save()
        # Automatically assign the creator as workspace admin
        WorkspaceMember.objects.get_or_create(
            workspace=workspace,
            user=self.request.user,
            defaults={'role': 'admin'}
        )
