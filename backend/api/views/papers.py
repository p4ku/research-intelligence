from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from research_intelligence.models import Paper, WorkspaceMember
from ..serializers.papers import PaperSerializer
from ..pagination import StandardResultsSetPagination


@extend_schema(
    tags=['Literature & Papers'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter papers by workspace UUID'),
        OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.QUERY, description='Alias for workspace filter'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter papers by PipelineRun UUID'),
        OpenApiParameter(name='screening_status', type=str, location=OpenApiParameter.QUERY, description='Filter by screening status (e.g. accepted, rejected)'),
    ]
)
class PaperViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Explore papers ingested in weekly batch runs.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = PaperSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ['created_at', 'title', 'screening_status', 'signal_score', 'doi', 'arxiv_id']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        user = self.request.user
        base_qs = Paper.objects.select_related('workspace', 'pipeline_run').prefetch_related('metrics')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)

        screening_status = self.request.query_params.get('screening_status')
        if screening_status:
            qs = qs.filter(screening_status=screening_status)

        pipeline_run_id = self.request.query_params.get('pipeline_run') or self.request.query_params.get('pipeline_run_id')
        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            from django.db.models import Q
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                qs = qs.filter(Q(pipeline_run_id=pr_uuid) | Q(reprocessed_runs__id=pr_uuid)).distinct()
            except (ValueError, TypeError):
                qs = qs.none()

        return qs.order_by('-created_at', '-id')

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Direct authenticated PDF binary stream"),
            404: OpenApiResponse(description="PDF binary file not available in storage for this paper"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
        }
    )
    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request, pk=None):
        paper = self.get_object()
        if not paper.original_pdf_path or not default_storage.exists(paper.original_pdf_path):
            return Response(
                {"error": "PDF binary file not available in storage for this paper."},
                status=status.HTTP_404_NOT_FOUND
            )

        file_handle = default_storage.open(paper.original_pdf_path, 'rb')
        response = FileResponse(file_handle, content_type='application/pdf')
        safe_filename = f"{paper.arxiv_id or str(paper.id)[:8]}.pdf"
        response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
        return response
