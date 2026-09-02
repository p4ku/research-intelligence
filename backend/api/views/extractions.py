from rest_framework import viewsets, serializers, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter
from research_intelligence.models import Extraction, WorkspaceMember
from ..pagination import StandardResultsSetPagination


class ExtractionSerializer(serializers.ModelSerializer):
    exit_metric = serializers.ReadOnlyField()

    class Meta:
        model = Extraction
        fields = [
            'id', 'workspace', 'paper', 'extraction_definition',
            'category', 'fields_data', 'is_hitl_validated',
            'version_info', 'validation_status', 'review_required',
            'confidence_score', 'confidence_method', 'exit_metric',
            'created_at'
        ]


@extend_schema(
    tags=['Dynamic Extractions'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter extractions by workspace UUID'),
        OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.QUERY, description='Alias for workspace filter'),
        OpenApiParameter(name='paper', type=str, location=OpenApiParameter.QUERY, description='Filter extractions by Paper UUID'),
        OpenApiParameter(name='paper_id', type=str, location=OpenApiParameter.QUERY, description='Alias for paper filter'),
        OpenApiParameter(name='definition', type=str, location=OpenApiParameter.QUERY, description='Filter extractions by definition UUID'),
        OpenApiParameter(name='definition_id', type=str, location=OpenApiParameter.QUERY, description='Alias for definition filter'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter extractions by PipelineRun UUID (including reprocessed papers)'),
        OpenApiParameter(name='pipeline_run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
        OpenApiParameter(name='run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
    ]
)
class ExtractionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists extracted claims and parameters matching schema settings.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = ExtractionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ['created_at', 'category', 'validation_status', 'confidence_score']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        user = self.request.user
        base_qs = Extraction.objects.select_related('paper', 'extraction_definition', 'workspace')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)

        paper_id = self.request.query_params.get('paper') or self.request.query_params.get('paper_id')
        if paper_id:
            qs = qs.filter(paper_id=paper_id)

        def_id = self.request.query_params.get('definition') or self.request.query_params.get('definition_id')
        if def_id:
            qs = qs.filter(extraction_definition_id=def_id)

        pipeline_run_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
            or self.request.query_params.get('run_id')
        )
        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                qs = qs.filter(paper__metrics__pipeline_run_id=pr_uuid).distinct()
            except (ValueError, TypeError):
                qs = qs.none()

        return qs.order_by('-created_at')
