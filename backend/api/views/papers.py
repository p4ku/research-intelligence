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
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter papers by PipelineRun UUID'),
        OpenApiParameter(name='screening_status', type=str, location=OpenApiParameter.QUERY, description='Filter by screening status (e.g. accepted, rejected)'),
        OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY, description='Full-text search in title, authors, abstract, DOI, or arXiv ID'),
    ]
)
class PaperViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Explore papers ingested in weekly batch runs.
    Scoped to workspaces the authenticated user is a member of.
    """
    queryset = Paper.objects.none()
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
        user_ws_ids = set(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return Paper.objects.none()
        qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            if str(ws_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
                if ws_uuid not in user_ws_ids:
                    return qs.none()
                qs = qs.filter(workspace_id=ws_uuid)
            except (ValueError, TypeError):
                return qs.none()

        search_query = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search_query and str(search_query).strip():
            from django.db.models import Q
            term = str(search_query).strip()
            qs = qs.filter(
                Q(title__icontains=term) |
                Q(authors__icontains=term) |
                Q(abstract__icontains=term) |
                Q(doi__icontains=term) |
                Q(arxiv_id__icontains=term)
            )

        pipeline_run_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
        )
        pr_uuid = None
        screening_status = self.request.query_params.get('screening_status')
        ordering = self.request.query_params.get('ordering')

        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            from django.db.models import Prefetch
            if str(pipeline_run_id).lower() == 'latest':
                from research_intelligence.models import PipelineRun
                run_filter = {}
                if ws_id and str(ws_id).lower() not in ('undefined', 'null', ''):
                    run_filter['workspace_id'] = ws_id
                else:
                    run_filter['workspace_id__in'] = user_ws_ids
                latest_run = (
                    PipelineRun.objects.filter(**run_filter)
                    .exclude(status__in=['failed', 'aborted'])
                    .order_by('-started_at', '-id')
                    .first()
                )
                if not latest_run:
                    latest_run = (
                        PipelineRun.objects.filter(**run_filter)
                        .order_by('-started_at', '-id')
                        .first()
                    )
                if latest_run:
                    pr_uuid = latest_run.id
                else:
                    return qs.none()
            else:
                try:
                    pr_uuid = uuid.UUID(str(pipeline_run_id))
                except (ValueError, TypeError):
                    return qs.none()

            action = getattr(self, 'action', None)
            if action not in ['comments', 'messages']:
                filter_kwargs = {'metrics__pipeline_run_id': pr_uuid}
                if screening_status:
                    if str(screening_status).lower() in ('passed', 'all_passed'):
                        filter_kwargs['metrics__screening_status__in'] = ['abstract_passed', 'full_text_passed', 'accepted']
                    else:
                        filter_kwargs['metrics__screening_status'] = screening_status
                qs = qs.filter(**filter_kwargs).distinct()

            qs = qs.prefetch_related(
                Prefetch('metrics', queryset=PaperMetric.objects.filter(pipeline_run_id=pr_uuid).select_related('pipeline_run').order_by('-created_at'))
            )

            if action != 'scorecard':
                from django.db.models import F
                if ordering in ('signal_score', '+signal_score'):
                    return qs.order_by('metrics__signal_score', '-created_at', '-id')
                elif ordering == '-signal_score':
                    return qs.order_by(F('metrics__signal_score').desc(nulls_last=True), '-created_at', '-id')

            return qs.order_by('-created_at', '-id')

        # Workspace-level queries (no specific pipeline run):
        from django.db.models import Prefetch
        qs = qs.prefetch_related(
            Prefetch('metrics', queryset=PaperMetric.objects.select_related('pipeline_run').order_by('-created_at'))
        )

        from django.db.models import Subquery, OuterRef, F
        if screening_status:
            latest_status = Subquery(
                PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at').values('screening_status')[:1]
            )
            if str(screening_status).lower() in ('passed', 'all_passed'):
                qs = qs.annotate(_latest_status=latest_status).filter(_latest_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
            else:
                qs = qs.annotate(_latest_status=latest_status).filter(_latest_status=screening_status)

        if ordering in ('signal_score', '+signal_score', '-signal_score'):
            latest_score = Subquery(
                PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at').values('signal_score')[:1]
            )
            qs = qs.annotate(_latest_score=latest_score)
            if ordering == '-signal_score':
                return qs.order_by(F('_latest_score').desc(nulls_last=True), '-created_at', '-id')
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
            OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID or "latest" to scope evaluation and narrative report'),
        ],
        description="Full paper scorecard with run-scoped evaluation metrics, complete extraction fields_data, definition schemas/exit metrics, and narrative report context.",
        responses={200: OpenApiResponse(description="Full paper scorecard with run-scoped evaluation metrics, extraction fields_data, dimensions, and narrative report context.")}
    )
    @extend_schema(
        tags=['Literature & Papers'],
        parameters=[
            OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.QUERY, description='Optional Workspace UUID to filter papers'),
            OpenApiParameter(name='screening', type=str, location=OpenApiParameter.QUERY, description='Filter by screening status (passed, all, or specific status)'),
            OpenApiParameter(name='ordering', type=str, location=OpenApiParameter.QUERY, description='Sort field (-signal_score, signal_score, -created_at, etc.)'),
            OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY, description='Search query across title, authors, abstract, DOI, arXiv ID'),
            OpenApiParameter(name='starred', type=str, location=OpenApiParameter.QUERY, description='1 for starred only, 0 for all'),
            OpenApiParameter(name='min_score', type=float, location=OpenApiParameter.QUERY, description='Minimum signal score'),
            OpenApiParameter(name='within_days', type=int, location=OpenApiParameter.QUERY, description='Ingested within N days of newest paper'),
            OpenApiParameter(name='min_trl', type=int, location=OpenApiParameter.QUERY, description='Minimum TRL level (1-9)'),
            OpenApiParameter(name='max_trl', type=int, location=OpenApiParameter.QUERY, description='Maximum TRL level (1-9)'),
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, description='Page number'),
            OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, description='Items per page'),
        ],
        description="Paginated list of papers in full ScoredPaper scorecard format across workspaces with corpus-wide facets.",
        responses={200: OpenApiResponse(description="Paginated scorecard list with facets.")}
    )
    @action(detail=False, methods=['get'], url_path='scorecard')
    def scorecard_list(self, request):
        from .scorecard import build_papers_scorecard_list_response
        return build_papers_scorecard_list_response(request)

    @extend_schema(
        tags=['Literature & Papers'],
        parameters=[
            OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID to scope run metrics'),
        ],
        description="Full paper scorecard with run-scoped evaluation metrics, complete extraction fields_data, definition schemas/exit metrics, and narrative report context.",
        responses={200: OpenApiResponse(description="Full paper scorecard with run-scoped evaluation metrics, extraction fields_data, dimensions, and narrative report context.")}
    )
    @action(detail=True, methods=['get'], url_path='scorecard')
    def scorecard(self, request, pk=None):
        from .scorecard import build_paper_scorecard_response
        paper = self.get_object()
        return build_paper_scorecard_response(paper, request)

    @extend_schema(
        tags=['Literature & Papers'],
        parameters=[
            OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID to scope run metrics'),
        ],
        description="Lightweight neighbours (prev, next, position, total) in signal score order for paper navigation.",
        responses={200: OpenApiResponse(description="Paper neighbours within workspace in signal score order.")}
    )
    @action(detail=True, methods=['get'], url_path='neighbours')
    def neighbours(self, request, pk=None):
        from .scorecard import build_paper_neighbours_response
        paper = self.get_object()
        return build_paper_neighbours_response(paper, request)

    @extend_schema(
        tags=['Literature & Papers'],
        parameters=[
            OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID to scope run comments'),
        ],
        description="List or create collaboration comments and discussion messages on this paper.",
    )
    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        paper = self.get_object()
        pr_param = (
            request.query_params.get('pipeline_run')
            or request.query_params.get('pipeline_run_id')
            or request.query_params.get('run_id')
            or (request.data.get('pipeline_run') if hasattr(request, 'data') and isinstance(request.data, dict) else None)
        )
        if request.method == 'GET':
            from api.serializers.comments import get_paper_messages_payload
            data = get_paper_messages_payload(paper, target_pr_id=pr_param, request=request)
            return Response(data, status=status.HTTP_200_OK)

        elif request.method == 'POST':
            from api.serializers.comments import PaperCommentSerializer
            from research_intelligence.models import PaperComment
            import uuid

            content = (request.data.get('content') or '').strip()
            if not content:
                return Response({'error': 'Content is required.'}, status=status.HTTP_400_BAD_REQUEST)

            comment_type = request.data.get('comment_type', PaperComment.TYPE_GENERAL)
            parent_id = request.data.get('parent_id')
            pr_uuid = None
            if pr_param and str(pr_param).lower() not in ('undefined', 'null', ''):
                try:
                    pr_uuid = uuid.UUID(str(pr_param))
                except (ValueError, TypeError):
                    pr_uuid = None

            comment = PaperComment.objects.create(
                workspace=paper.workspace,
                paper=paper,
                pipeline_run_id=pr_uuid,
                user=request.user,
                parent_id=parent_id,
                content=content,
                comment_type=comment_type,
            )
            serializer = PaperCommentSerializer(comment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def messages(self, request, pk=None):
        """Alias action for /comments/."""
        return self.comments(request, pk=pk)




@extend_schema(
    tags=['Literature & Papers'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter metrics by workspace UUID'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter by PipelineRun UUID'),
        OpenApiParameter(name='paper', type=str, location=OpenApiParameter.QUERY, description='Filter by Paper UUID'),
        OpenApiParameter(name='screening_status', type=str, location=OpenApiParameter.QUERY, description='Filter by screening status (e.g. accepted, rejected)'),
    ]
)
class PaperMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Explore paper-level evaluations, screening statuses, dynamic metric dictionaries,
    and composite signal scores evaluated per pipeline run.
    """
    queryset = PaperMetric.objects.none()
    serializer_class = PaperMetricSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ['created_at', 'signal_score', 'screening_status']
    ordering = ['-signal_score', '-created_at', '-id']

    def filter_queryset(self, queryset):
        ordering = self.request.query_params.get('ordering')
        if ordering == '-signal_score' or not ordering:
            from django.db.models import F
            return queryset.order_by(F('signal_score').desc(nulls_last=True), '-created_at', '-id')
        return super().filter_queryset(queryset)

    def get_queryset(self):
        user = self.request.user
        base_qs = PaperMetric.objects.select_related('paper', 'pipeline_run', 'workspace')
        user_ws_ids = set(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return PaperMetric.objects.none()
        qs = base_qs.filter(workspace_id__in=user_ws_ids)

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            if str(ws_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
                if ws_uuid not in user_ws_ids:
                    return qs.none()
                qs = qs.filter(workspace_id=ws_uuid)
            except (ValueError, TypeError):
                return qs.none()

        pr_id = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
        )
        if pr_id:
            if str(pr_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            if str(pr_id).lower() == 'latest':
                from research_intelligence.models import PipelineRun
                run_filter = {}
                if ws_id and str(ws_id).lower() not in ('undefined', 'null', ''):
                    run_filter['workspace_id'] = ws_id
                else:
                    run_filter['workspace_id__in'] = user_ws_ids
                latest_run = (
                    PipelineRun.objects.filter(**run_filter)
                    .exclude(status__in=['failed', 'aborted'])
                    .order_by('-started_at', '-id')
                    .first()
                )
                if not latest_run:
                    latest_run = (
                        PipelineRun.objects.filter(**run_filter)
                        .order_by('-started_at', '-id')
                        .first()
                    )
                if latest_run:
                    qs = qs.filter(pipeline_run_id=latest_run.id)
                else:
                    return qs.none()
            else:
                try:
                    pr_uuid = uuid.UUID(str(pr_id))
                    qs = qs.filter(pipeline_run_id=pr_uuid)
                except (ValueError, TypeError):
                    return qs.none()

        paper_id = self.request.query_params.get('paper') or self.request.query_params.get('paper_id')
        if paper_id:
            if str(paper_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                p_uuid = uuid.UUID(str(paper_id))
                qs = qs.filter(paper_id=p_uuid)
            except (ValueError, TypeError):
                return qs.none()

        screening_status = self.request.query_params.get('screening_status')
        if screening_status:
            if str(screening_status).lower() in ('passed', 'all_passed'):
                qs = qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
            else:
                qs = qs.filter(screening_status=screening_status)

        return qs
