from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from research_intelligence.models import Scraper, WorkspaceMember
from ..serializers.workspaces import ScraperSerializer


@extend_schema(tags=['Scrapers Configuration'])
class ScraperViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Scraper configurations.
    Accessible only to members of the workspace.
    """
    serializer_class = ScraperSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'provider', 'is_active', 'search_query']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return Scraper.objects.none()
        qs = Scraper.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            if str(ws_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
                qs = qs.filter(workspace_id=ws_uuid)
            except (ValueError, TypeError):
                return qs.none()

        return qs

    def perform_create(self, serializer):
        workspace = serializer.validated_data.get('workspace')
        if not workspace:
            raise PermissionDenied("Workspace is required.")
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        # Ensure updated scraper's workspace access
        scraper = self.get_object()
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=scraper.workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        # Ensure workspace access for deletion
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=instance.workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        instance.delete()
