from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter
from research_intelligence.models import NarrativeReport, WorkspaceMember
from ..serializers.reports import NarrativeReportSerializer
from ..pagination import StandardResultsSetPagination


@extend_schema(
    tags=['Narrative & Executive Reports'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter reports by workspace UUID'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter reports by PipelineRun UUID'),
    ]
)
class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Weekly compiled narrative briefings generated autonomously by the SLR pipeline.
    Read-only: reports are synthesized by the reporting engine.
    Scoped to workspaces the authenticated user is a member of.
    """
    queryset = NarrativeReport.objects.none()
    serializer_class = NarrativeReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'head', 'options']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        user = self.request.user
        user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return NarrativeReport.objects.none()
        qs = NarrativeReport.objects.select_related('workspace', 'pipeline_run').filter(workspace_id__in=user_ws_ids).order_by('-created_at')

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            if str(ws_id).lower() in ('undefined', 'null', ''):
                return NarrativeReport.objects.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
            except (ValueError, TypeError):
                return NarrativeReport.objects.none()
            if ws_uuid not in user_ws_ids:
                return NarrativeReport.objects.none()
            qs = qs.filter(workspace_id=ws_uuid)

        pipeline_run_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
        )
        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                qs = qs.filter(pipeline_run_id=pr_uuid)
            except (ValueError, TypeError):
                qs = qs.none()

        return qs
