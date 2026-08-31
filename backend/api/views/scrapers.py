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
        if getattr(user, 'is_superuser', False):
            return Scraper.objects.all().order_by('-created_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return Scraper.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')

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
                raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        # Ensure updated scraper's workspace access
        scraper = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=scraper.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        # Ensure workspace access for deletion
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage scrapers in this workspace.")
        instance.delete()
