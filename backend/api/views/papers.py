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
            if str(ws_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
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
                elif not getattr(user, 'is_superuser', False):
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

            filter_kwargs = {'metrics__pipeline_run_id': pr_uuid}
            if screening_status:
                filter_kwargs['metrics__screening_status'] = screening_status

            qs = qs.filter(**filter_kwargs).distinct().prefetch_related(
                Prefetch('metrics', queryset=PaperMetric.objects.filter(pipeline_run_id=pr_uuid).select_related('pipeline_run').order_by('-created_at'))
            )

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
        description="One paper in the scorecard shape, with its workspace summary.",
    )
    @action(detail=True, methods=['get'], url_path='scorecard')
    def scorecard(self, request, pk=None):
        paper = self.get_object()
        paper_serializer = PaperSerializer(paper, context={'request': request})
        paper_data = paper_serializer.data

        from research_intelligence.models import Extraction, ExtractionDefinition
        extractions = list(Extraction.objects.filter(paper=paper).select_related('extraction_definition').order_by('-created_at'))
        definitions = list(ExtractionDefinition.objects.filter(workspace=paper.workspace, is_active=True).order_by('created_at'))

        raw_authors = paper.authors or ''
        authors_list = [a.strip() for a in raw_authors.split(',') if a.strip()] if raw_authors else []

        dimensions = []
        ext_by_def = {}
        for e in extractions:
            if e.extraction_definition_id and e.extraction_definition_id not in ext_by_def:
                ext_by_def[e.extraction_definition_id] = e
        for d in definitions:
            e = ext_by_def.get(d.id)
            val = None
            if e and e.fields_data and isinstance(e.fields_data, dict):
                val = next(iter(e.fields_data.values()), None)
            dimensions.append({
                'key': d.name.lower().replace(' ', '_'),
                'label': d.name,
                'value': str(val) if val is not None else None,
                'definition_id': str(d.id),
                'confidence': float(e.confidence_score) if (e and e.confidence_score is not None) else None,
                'is_hitl': bool(e.is_hitl_validated) if e else False,
            })

        # Include any extractions on this paper that don't match active definitions
        matched_ext_ids = {e.id for e in ext_by_def.values() if e}
        for e in extractions:
            if e.id not in matched_ext_ids:
                val = None
                if e.fields_data and isinstance(e.fields_data, dict):
                    val = next(iter(e.fields_data.values()), None)
                dimensions.append({
                    'key': (e.category or 'custom').lower().replace(' ', '_'),
                    'label': e.category or 'Custom Extraction',
                    'value': str(val) if val is not None else None,
                    'definition_id': str(e.extraction_definition_id) if e.extraction_definition_id else None,
                    'confidence': float(e.confidence_score) if (e and e.confidence_score is not None) else None,
                    'is_hitl': bool(e.is_hitl_validated),
                })

        scored = {
            'id': str(paper.id),
            'workspace_id': str(paper.workspace_id),
            'pipeline_run_id': paper_data.get('pipeline_run') or '',
            'title': paper.title,
            'authors': authors_list,
            'authors_raw': raw_authors,
            'abstract': paper.abstract or '',
            'doi': paper.doi or None,
            'arxiv_id': paper.arxiv_id or None,
            'source': paper.source_database or '',
            'screening_status': paper_data.get('screening_status') or 'pending',
            'screening_reasoning': paper_data.get('screening_reasoning') or None,
            'signal_score': paper_data.get('signal_score'),
            'signal_score_details': paper_data.get('signal_score_details'),
            'dimensions': dimensions,
            'pdf_key': paper.original_pdf_path or None,
            'markdown_key': paper.converted_md_path or None,
            'pdf_url': paper.source_url,
            'source_url': paper.source_url,
            'is_benchmark': bool(paper_data.get('is_evaluation_benchmark', False)),
            'evaluation_label': paper_data.get('evaluation_label'),
            'created_at': paper.created_at.isoformat(),
        }

        ws_summary = {
            'id': str(paper.workspace.id),
            'name': paper.workspace.name,
            'definitions': [
                {
                    'id': str(d.id),
                    'name': d.name,
                    'key': d.name.lower().replace(' ', '_'),
                    'is_active': d.is_active,
                    'max': None,
                    'is_trl': 'trl' in d.name.lower(),
                }
                for d in definitions
            ],
            'scrapers_count': paper.workspace.scrapers.count(),
        }

        return Response({'workspace': ws_summary, 'paper': scored})


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
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = base_qs.filter(workspace_id__in=user_ws_ids)

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
                elif not getattr(user, 'is_superuser', False):
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
            qs = qs.filter(screening_status=screening_status)

        return qs
