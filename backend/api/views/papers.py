from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from research_intelligence.models import Paper, PaperMetric, WorkspaceMember
from ..serializers.papers import PaperSerializer, PaperMetricSerializer
from ..pagination import StandardResultsSetPagination


@extend_schema(
    tags=['Literature & Papers'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter papers by workspace UUID'),
        OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.QUERY, description='Alias for workspace filter'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter papers by PipelineRun UUID'),
        OpenApiParameter(name='pipeline_run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
        OpenApiParameter(name='run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
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
    ordering_fields = ['created_at', 'title', 'doi', 'arxiv_id']
    ordering = ['-created_at', '-id']

    def filter_queryset(self, queryset):
        ordering = self.request.query_params.get('ordering')
        if ordering in ('signal_score', '+signal_score', '-signal_score'):
            return queryset
        return super().filter_queryset(queryset)

    def get_queryset(self):
        user = self.request.user
        base_qs = Paper.objects.select_related('workspace')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)

        pipeline_run_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
            or self.request.query_params.get('run_id')
        )
        pr_uuid = None
        screening_status = self.request.query_params.get('screening_status')
        ordering = self.request.query_params.get('ordering')

        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            from django.db.models import Prefetch
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
            except (ValueError, TypeError):
                return qs.none()

            filter_kwargs = {'metrics__pipeline_run_id': pr_uuid}
            if screening_status:
                filter_kwargs['metrics__screening_status'] = screening_status

            qs = qs.filter(**filter_kwargs).distinct().prefetch_related(
                Prefetch('metrics', queryset=PaperMetric.objects.filter(pipeline_run_id=pr_uuid))
            )

            if ordering in ('signal_score', '+signal_score'):
                return qs.order_by('metrics__signal_score', '-created_at', '-id')
            elif ordering == '-signal_score':
                return qs.order_by('-metrics__signal_score', '-created_at', '-id')

            return qs.order_by('-created_at', '-id')

        # Workspace-level queries (no specific pipeline run):
        qs = qs.prefetch_related('metrics')

        from django.db.models import Subquery, OuterRef
        if screening_status:
            latest_status = Subquery(
                PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at').values('screening_status')[:1]
            )
            qs = qs.annotate(_latest_status=latest_status).filter(_latest_status=screening_status)

        if ordering in ('signal_score', '+signal_score', '-signal_score'):
            latest_score = Subquery(
                PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at').values('signal_score')[:1]
            )
            qs = qs.annotate(_latest_score=latest_score)
            if ordering == '-signal_score':
                return qs.order_by('-_latest_score', '-created_at', '-id')
            return qs.order_by('_latest_score', '-created_at', '-id')

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


@extend_schema(
    tags=['Literature & Papers'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter metrics by workspace UUID'),
        OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.QUERY, description='Alias for workspace filter'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter by PipelineRun UUID'),
        OpenApiParameter(name='pipeline_run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
        OpenApiParameter(name='run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run filter'),
        OpenApiParameter(name='paper', type=str, location=OpenApiParameter.QUERY, description='Filter by Paper UUID'),
        OpenApiParameter(name='paper_id', type=str, location=OpenApiParameter.QUERY, description='Alias for paper filter'),
        OpenApiParameter(name='screening_status', type=str, location=OpenApiParameter.QUERY, description='Filter by screening status (e.g. accepted, rejected)'),
    ]
)
class PaperMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Explore paper-level evaluations, screening statuses, dynamic metric dictionaries,
    and composite signal scores evaluated per pipeline run.
    """
    serializer_class = PaperMetricSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ['created_at', 'signal_score', 'screening_status']
    ordering = ['-signal_score', '-created_at', '-id']

    def get_queryset(self):
        user = self.request.user
        base_qs = PaperMetric.objects.select_related('paper', 'pipeline_run', 'workspace')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)

        pr_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
            or self.request.query_params.get('run_id')
        )
        if pr_id and str(pr_id).lower() not in ('undefined', 'null', ''):
            qs = qs.filter(pipeline_run_id=pr_id)

        paper_id = self.request.query_params.get('paper') or self.request.query_params.get('paper_id')
        if paper_id:
            qs = qs.filter(paper_id=paper_id)

        screening_status = self.request.query_params.get('screening_status')
        if screening_status:
            qs = qs.filter(screening_status=screening_status)

        return qs
