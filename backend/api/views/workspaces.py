from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from research_intelligence.models import Workspace, WorkspaceMember, ExtractionDefinition
from ..serializers.workspaces import WorkspaceSerializer, ExtractionDefinitionSerializer


@extend_schema(tags=['Workspaces Management'])
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace (Projects) and prompt limits configurations.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'monthly_usd_limit']
    ordering = ['-created_at']

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

    def perform_update(self, serializer):
        workspace = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("Only workspace admins and managers can modify workspace settings.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance, user=user, role='admin'
            ).exists()
            if not has_access:
                raise PermissionDenied("Only workspace admins can delete this workspace.")

        # Purge workspace storage artifacts recursively
        try:
            from research_intelligence.admin_views.storage_browser import _recursive_delete_dir
            _recursive_delete_dir(f"workspaces/{instance.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not purge workspace storage directory: {e}")

        instance.delete()


@extend_schema(tags=['Extraction Definitions'])
class ExtractionDefinitionViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for dynamic Extraction Definitions within a workspace.
    """
    serializer_class = ExtractionDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'version', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return ExtractionDefinition.objects.all().order_by('-created_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return ExtractionDefinition.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')

    def perform_create(self, serializer):
        workspace = serializer.validated_data.get('workspace')
        if not workspace:
            raise PermissionDenied("Workspace is required.")
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=obj.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        instance.delete()

