from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema
from research_intelligence.models import NarrativeReport, WorkspaceMember
from ..serializers.reports import NarrativeReportSerializer


@extend_schema(tags=['Narrative & Executive Reports'])
class ReportViewSet(viewsets.ModelViewSet):
    """
    Weekly compiled narrative briefings.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = NarrativeReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return NarrativeReport.objects.all()
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return NarrativeReport.objects.filter(workspace_id__in=user_ws_ids)
