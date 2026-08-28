from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema
from research_intelligence.models import Paper, WorkspaceMember
from ..serializers.papers import PaperSerializer


@extend_schema(tags=['Literature & Papers'])
class PaperViewSet(viewsets.ModelViewSet):
    """
    Explore papers ingested in weekly batch runs.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = PaperSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base_qs = Paper.objects.select_related('workspace', 'pipeline_run').prefetch_related('metrics')
        if getattr(user, 'is_superuser', False):
            return base_qs.all()
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return base_qs.filter(workspace_id__in=user_ws_ids)
