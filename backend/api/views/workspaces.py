from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from research_intelligence.models import Workspace, WorkspaceMember, ExtractionDefinition, PaperMetric, PipelineRun
from ..serializers.workspaces import WorkspaceSerializer, ExtractionDefinitionSerializer
from ..serializers.pipeline_runs import StartPipelineRunSerializer


@extend_schema(
    tags=['Workspaces Management'],
    description="""
Manage SLR Workspace Projects, screening criteria, screening LLM engines, and default processing policies.

### Key Fields & Policies:
- **`reprocess_existing`** (boolean): Default workspace policy for pipeline runs. If `True`, pipeline runs re-evaluate and re-screen existing workspace papers even if no new papers are found from scrapers. This can be overridden per individual run via `configuration_override['reprocess_existing']` in API / MCP.
- **`skip_abstract_screening`** (boolean): If `True`, skips Abstract Screening and routes all candidate papers directly to multimodal Full-Text Screening.
- **`subscribers`**: Email recipients receiving automated execution reports and error alerts.
- **`workflow_schedules`**: Recurring (cron) and one-off execution schedules managed via `/api/schedules/`.
"""
)
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace (Projects), dual-stage criteria, and processing policies.
    Scoped to workspaces the authenticated user is a member of.
    """
    queryset = Workspace.objects.none()
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'monthly_usd_limit']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        action = getattr(self, 'action', None)
        if action in ('list', 'retrieve'):
            base_qs = Workspace.objects.prefetch_related('subscribers', 'scrapers', 'extraction_definitions').order_by('-created_at')
        else:
            base_qs = Workspace.objects.order_by('-created_at')
        user_ws_members = dict(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', 'role'))
        if not user_ws_members:
            return Workspace.objects.none()
        self.request._user_ws_roles = user_ws_members
        return base_qs.filter(id__in=user_ws_members.keys())

    def perform_create(self, serializer):
        workspace = serializer.save()
        # Automatically assign the creator as workspace admin
        WorkspaceMember.objects.get_or_create(
            workspace=workspace,
            user=self.request.user,
            defaults={'role': 'admin'}
        )

    def perform_update(self, serializer):
        workspace = self.get_object()
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("Only workspace admins and managers can modify workspace settings.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=instance, user=user, role='admin'
        ).exists()
        if not has_access:
            raise PermissionDenied("Only workspace admins can delete this workspace.")

        # Purge workspace storage artifacts recursively
        try:
            from research_intelligence.admin_views.storage_browser import _recursive_delete_dir
            _recursive_delete_dir(f"workspaces/{instance.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not purge workspace storage directory: {e}")

        instance.delete()

    @extend_schema(
        tags=['Workspaces Management', 'Literature & Papers'],
        description="List papers ingested into this workspace, optionally filtered by pipeline_run or screening_status.",
    )
    @action(detail=True, methods=['get'], url_path='papers')
    def papers(self, request, pk=None):
        workspace = self.get_object()
        from ..views.papers import PaperViewSet
        from ..serializers.papers import PaperSerializer
        from rest_framework.response import Response

        paper_view = PaperViewSet()
        paper_view.request = request
        paper_view.format_kwarg = None

        # Scope query to this workspace
        q_params = request.query_params.copy()
        q_params['workspace'] = str(workspace.id)
        request._request.GET = q_params

        qs = paper_view.get_queryset().filter(workspace=workspace)
        page = paper_view.paginate_queryset(qs)
        if page is not None:
            serializer = PaperSerializer(page, many=True, context={'request': request, 'workspace': workspace})
            return paper_view.get_paginated_response(serializer.data)
        serializer = PaperSerializer(qs, many=True, context={'request': request, 'workspace': workspace})
        return Response(serializer.data)

    @extend_schema(
        tags=['Workspaces Management', 'Literature & Papers'],
        parameters=[
            OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID or "latest" to scope evaluation'),
            OpenApiParameter(name='run_id', type=str, location=OpenApiParameter.QUERY, description='Alias for pipeline_run parameter'),
            OpenApiParameter(name='screening_status', type=str, location=OpenApiParameter.QUERY, description='Filter papers by screening status (e.g. passed, accepted, rejected)'),
            OpenApiParameter(name='screening', type=str, location=OpenApiParameter.QUERY, description='Alias for screening_status parameter'),
            OpenApiParameter(name='ordering', type=str, location=OpenApiParameter.QUERY, description='Sort ordering (e.g. signal_score, -signal_score, title, -title, created_at, -created_at)'),
            OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY, description='Search query across paper title, authors, abstract, doi, arxiv_id'),
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, description='Page number'),
            OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, description='Page size'),
        ],
        description="Dynamic Workspace Scorecard containing all evaluated papers with run-scoped metrics and rich dimension details.",
        responses={200: OpenApiResponse(description="Dynamic Workspace Scorecard containing all evaluated papers with run-scoped metrics, dimensions, and filter statistics.")},
    )
    @action(detail=True, methods=['get'], url_path='scorecard')
    def scorecard(self, request, pk=None):
        from .scorecard import build_workspace_scorecard_response
        workspace = self.get_object()
        return build_workspace_scorecard_response(workspace, request)

    @extend_schema(
        tags=['Workspaces Management', 'Pipeline Runs & Components'],
        description="Trigger an autonomous pipeline run for this specific workspace with optional date range parameters.",
        request=StartPipelineRunSerializer,
        responses={
            201: OpenApiResponse(description="Autonomous pipeline run started for workspace"),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            409: OpenApiResponse(description="Conflict - workspace at its concurrent-run limit, or this search window is already running"),
        }
    )
    @action(detail=True, methods=['post'], url_path='run-pipeline')
    def run_pipeline(self, request, pk=None):
        import json
        from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic
        from .pipeline_runs import start_error_response

        workspace = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['workspace_id'] = str(workspace.id)

        serializer = StartPipelineRunSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        valid_data = serializer.validated_data
        n_last_days = valid_data.get('n_last_days')
        res_json = start_pipeline_run_logic(
            user=request.user,
            workspace_id=str(workspace.id),
            name=valid_data.get('name'),
            limit=valid_data.get('limit'),
            query_prefix=valid_data.get('query_prefix'),
            skip_abstract_screening=valid_data.get('skip_abstract_screening'),
            notification_email=valid_data.get('notification_email'),
            reprocess_existing=valid_data.get('reprocess_existing'),
            autonomous=valid_data.get('autonomous', True),
            start_date=valid_data.get('start_date'),
            end_date=valid_data.get('end_date'),
            n_last_days=n_last_days
        )
        try:
            res_data = json.loads(res_json)
        except Exception:
            res_data = {"raw_response": res_json}

        if isinstance(res_data, dict) and res_data.get("status") == "error":
            return start_error_response(res_data)

        return Response(res_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Workspaces Management'],
        description="Export full workspace configuration as a portable JSON template bundle.",
        responses={
            200: OpenApiResponse(description="Workspace configuration template bundle"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
            404: OpenApiResponse(description="Workspace not found"),
        }
    )
    @action(detail=True, methods=['get'], url_path='export-configuration')
    def export_configuration(self, request, pk=None):
        from research_intelligence.services.workspace_service import serialize_workspace_configuration
        from django.utils.timezone import now
        workspace = self.get_object()
        ws_data = serialize_workspace_configuration(workspace)
        export_payload = {
            "version": "1.0",
            "exported_at": now().isoformat(),
            "workspaces_count": 1,
            "workspaces": [ws_data],
            "workspace": ws_data,
        }
        return Response(export_payload, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Workspaces Management'],
        description="Import workspace configuration from a JSON template bundle (creates or updates workspaces, definitions, scrapers, subscribers).",
        responses={
            200: OpenApiResponse(description="Workspace configuration successfully imported"),
            400: OpenApiResponse(description="Bad request / Invalid JSON bundle"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
        }
    )
    @action(detail=False, methods=['post'], url_path='import-configuration')
    def import_configuration(self, request):
        from research_intelligence.services.workspace_service import import_workspace_configuration_bundle
        data = request.data
        if not data or not isinstance(data, (dict, list)):
            return Response({"error": "Invalid or missing JSON payload."}, status=status.HTTP_400_BAD_REQUEST)

        update_existing = True
        if isinstance(data, dict):
            update_existing = bool(data.get('overwrite_existing', data.get('update_existing', True)))

        try:
            stats = import_workspace_configuration_bundle(
                data=data,
                user=request.user,
                update_existing=update_existing,
            )
            serializable_stats = dict(stats)
            if "workspaces" in serializable_stats and isinstance(serializable_stats["workspaces"], list):
                serializable_stats["workspaces"] = [
                    {"id": str(w.id), "name": w.name} if hasattr(w, "id") else w
                    for w in serializable_stats["workspaces"]
                ]
            return Response({
                "status": "success",
                "message": "Workspace configuration imported successfully.",
                "stats": serializable_stats,
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({
                "status": "error",
                "error": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=['Workspaces Management', 'Scoring & Ranking'],
        description="Get scoring configuration, variables, weights, and worked example for this workspace.",
        responses={200: OpenApiResponse(description="Workspace scoring formula configuration, active variables, calculated weights, and top paper calculation example")},
    )
    @action(detail=True, methods=['get'], url_path='scoring')
    def scoring(self, request, pk=None):
        workspace = self.get_object()
        active_defs = list(workspace.extraction_definitions.filter(is_active=True).order_by('created_at'))
        active_count = len(active_defs)

        variables = [
            {
                "key": d.name.lower().replace(" ", "_"),
                "definition_id": str(d.id),
                "name": d.name,
                "max": None,
                "is_trl": "trl" in d.name.lower(),
            }
            for d in active_defs
        ]

        weights = [
            {
                "key": d.name.lower().replace(" ", "_"),
                "definition_id": str(d.id),
                "name": d.name,
                "weight": round(1000.0 / active_count) / 10.0 if active_count > 0 else 0,
            }
            for d in active_defs
        ]

        pm = (
            PaperMetric.objects.filter(workspace=workspace, signal_score__isnull=False)
            .select_related('paper')
            .order_by('-signal_score', '-created_at')
            .first()
        )
        example_obj = None
        if pm and pm.paper:
            example_obj = {
                "paper_id": str(pm.paper.id),
                "title": pm.paper.title,
                "signal_score": pm.signal_score,
                "variables": (pm.signal_score_details or {}).get("variables", {}),
            }

        return Response({
            "workspace_id": str(workspace.id),
            "code": workspace.signal_score_code or None,
            "code_source": "workspace" if workspace.signal_score_code else "stub",
            "variables": variables,
            "weights": weights,
            "weights_source": "stub",
            "example": example_obj,
        })

    @extend_schema(
        operation_id="workspace_editions_list",
        tags=['Workspaces Management', 'Briefings & Editions'],
        description="Paginated list of completed briefing editions for this workspace, newest first.",
        parameters=[
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, description='Page number (default: 1)'),
            OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, description='Number of editions per page (default: 20)'),
        ],
        responses={200: OpenApiResponse(description="Paginated list of completed briefing editions with surfaced papers")},
    )
    @action(detail=True, methods=['get'], url_path='editions')
    def editions(self, request, pk=None):
        workspace = self.get_object()
        completed_runs = list(
            PipelineRun.objects.filter(workspace=workspace, status='completed')
            .only(
                'id', 'workspace_id', 'completed_at', 'run_date', 'started_at',
                'status_message', 'total_papers_fetched', 'total_papers_passed_screening'
            )
            .order_by('-completed_at', '-id')
        )
        run_items = []
        for run in completed_runs:
            d = (run.completed_at or run.run_date or run.started_at).strftime('%Y-%m-%d')
            run_items.append((d, run))

        page_num = request.query_params.get('page', 1)
        page_size = int(request.query_params.get('page_size', 20))
        try:
            page_num = max(1, int(page_num))
        except (ValueError, TypeError):
            page_num = 1

        total_count = len(run_items)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        slice_items = run_items[start_idx:end_idx]

        target_runs = [run for _, run in slice_items]
        from collections import defaultdict
        papers_by_run = defaultdict(list)
        if target_runs:
            passed_pms = (
                PaperMetric.objects.filter(
                    pipeline_run__in=target_runs,
                    screening_status__in=['accepted', 'full_text_passed', 'abstract_passed']
                )
                .select_related('paper', 'pipeline_run')
                .only(
                    'id', 'pipeline_run_id', 'signal_score', 'screening_status', 'created_at',
                    'pipeline_run__id', 'pipeline_run__name',
                    'paper__id', 'paper__workspace_id', 'paper__title', 'paper__authors',
                    'paper__abstract', 'paper__doi', 'paper__arxiv_id', 'paper__source_database',
                    'paper__source_url', 'paper__original_pdf_path', 'paper__created_at'
                )
                .order_by('-signal_score', '-created_at')
            )
            for pm in passed_pms:
                if pm.paper:
                    authors_list = [a.strip() for a in (pm.paper.authors or '').split(',') if a.strip()]
                    source_url = pm.paper.source_url
                    if not source_url:
                        if pm.paper.arxiv_id:
                            source_url = f"https://arxiv.org/abs/{pm.paper.arxiv_id}"
                        elif pm.paper.doi:
                            source_url = f"https://doi.org/{pm.paper.doi}"

                    papers_by_run[pm.pipeline_run_id].append({
                        "id": str(pm.paper.id),
                        "workspace_id": str(pm.paper.workspace_id or workspace.id),
                        "pipeline_run_id": str(pm.pipeline_run_id),
                        "title": pm.paper.title,
                        "authors": authors_list,
                        "authors_raw": pm.paper.authors or '',
                        "abstract": pm.paper.abstract or '',
                        "doi": pm.paper.doi or None,
                        "arxiv_id": pm.paper.arxiv_id or None,
                        "source": pm.paper.source_database or 'arXiv',
                        "screening_status": pm.screening_status,
                        "screening_reasoning": None,
                        "abstract_screening_reasoning": None,
                        "full_text_screening_reasoning": None,
                        "signal_score": pm.signal_score,
                        "signal_score_details": None,
                        "dimensions": [],
                        "pdf_key": pm.paper.original_pdf_path or None,
                        "markdown_key": None,
                        "source_url": source_url,
                        "is_benchmark": False,
                        "evaluation_label": None,
                        "published_date": None,
                        "created_at": pm.paper.created_at.isoformat() if pm.paper.created_at else "",
                        "pipeline_run_name": pm.pipeline_run.name if (pm.pipeline_run and hasattr(pm.pipeline_run, 'name')) else None,
                    })

        results = []
        for d, run in slice_items:
            surfaced = papers_by_run.get(run.id, [])
            in_brief_text = (
                run.status_message
                or f"{workspace.name} briefing for {d}: {run.total_papers_fetched} papers ingested, {len(surfaced)} surfaced."
            )
            results.append({
                "run_id": str(run.id),
                "workspace_id": str(workspace.id),
                "workspace_name": workspace.name,
                "date": d,
                "title": f"{workspace.name} Briefing — {d}",
                "in_brief": in_brief_text,
                "in_brief_source": "template",
                "funnel": {
                    "fetched": run.total_papers_fetched or len(surfaced),
                    "passed_screening": run.total_papers_passed_screening or len(surfaced),
                    "surfaced": len(surfaced),
                },
                "papers": surfaced,
                "generated_at": (
                    run.completed_at.isoformat()
                    if (hasattr(run.completed_at, 'tzinfo') and run.completed_at.tzinfo)
                    else (run.completed_at.isoformat() + "Z")
                ) if run.completed_at else None,
            })

        next_url = None
        if end_idx < total_count:
            next_url = f"{request.build_absolute_uri(request.path)}?page={page_num + 1}&page_size={page_size}"
        prev_url = None
        if page_num > 1:
            prev_url = f"{request.build_absolute_uri(request.path)}?page={page_num - 1}&page_size={page_size}"

        return Response({
            "count": total_count,
            "next": next_url,
            "previous": prev_url,
            "results": results,
        })

    @extend_schema(
        operation_id="workspace_edition_detail",
        tags=['Workspaces Management', 'Briefings & Editions'],
        description="Detail of one briefing edition by date (YYYY-MM-DD), including screening exclusions.",
        parameters=[
            OpenApiParameter(name='workspace_id', type=str, location=OpenApiParameter.PATH, description='Target workspace UUID'),
            OpenApiParameter(name='edition_date', type=str, location=OpenApiParameter.PATH, description='Edition date in YYYY-MM-DD format'),
            OpenApiParameter(name='run_id', type=str, location=OpenApiParameter.QUERY, description='Optional PipelineRun UUID to select a specific run for that date'),
            OpenApiParameter(name='scope', type=str, location=OpenApiParameter.QUERY, description="Filter scope for edition papers: 'all' (default, returns both surfaced papers and exclusions), 'included' (surfaced papers only), or 'excluded' (exclusions only)"),
        ],
        responses={
            200: OpenApiResponse(description="Briefing edition details including surfaced papers, exclusions, and funnel counts"),
            400: OpenApiResponse(description="Bad request or invalid date format"),
            404: OpenApiResponse(description="Workspace or edition not found"),
        }
    )
    def edition_detail(self, request, workspace_id=None, edition_date=None, **kwargs):
        ws_id = workspace_id or kwargs.get('pk')
        if not ws_id:
            return Response({"error": "Workspace ID required"}, status=status.HTTP_400_BAD_REQUEST)

        self.kwargs['pk'] = ws_id
        workspace = self.get_object()
        request._audit_workspace = workspace
        if hasattr(request, '_request'):
            request._request._audit_workspace = workspace

        from datetime import datetime, time, timedelta
        from django.utils import timezone
        try:
            target_date = datetime.strptime(edition_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({"error": "Invalid date format. Expected YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.is_aware(timezone.now()):
            start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
            end_dt = start_dt + timedelta(days=1)
        else:
            start_dt = datetime.combine(target_date, time.min)
            end_dt = start_dt + timedelta(days=1)

        requested_run_id = request.query_params.get('run_id')
        target_run_uuid = None
        if requested_run_id and str(requested_run_id).lower() not in ('undefined', 'null', ''):
            import uuid
            try:
                target_run_uuid = uuid.UUID(str(requested_run_id))
            except (ValueError, TypeError):
                target_run_uuid = None

        from django.db.models import Q
        date_q = Q(workspace=workspace) & Q(status='completed') & (
            (Q(completed_at__gte=start_dt) & Q(completed_at__lt=end_dt)) |
            Q(run_date=target_date)
        )
        date_runs = (
            PipelineRun.objects.filter(date_q)
            .only(
                'id', 'workspace_id', 'completed_at', 'run_date', 'started_at', 'status_message',
                'total_papers_fetched', 'total_papers_passed_screening', 'name'
            )
            .order_by('-completed_at', '-id')
        )

        run = None
        if target_run_uuid:
            run = date_runs.filter(id=target_run_uuid).first()

        # If run_id was not provided, or does not exist on that date, fall back to the day's newest run
        if not run:
            run = date_runs.first()

        if not run:
            return Response(
                {"error": f"No completed briefing edition found for {edition_date}."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Parse scope parameter: 'all' (default), 'included', or 'excluded'
        raw_scope = (
            request.query_params.get('scope')
            or request.query_params.get('include')
            or request.query_params.get('papers')
            or ''
        ).strip().lower()

        inc_excl = request.query_params.get('include_exclusions')
        if inc_excl is not None and not raw_scope:
            if inc_excl.strip().lower() in ('false', '0', 'no'):
                raw_scope = 'included'
            elif inc_excl.strip().lower() in ('true', '1', 'yes'):
                raw_scope = 'all'

        if raw_scope not in ('all', 'included', 'excluded'):
            scope = 'all'
        else:
            scope = raw_scope

        include_surfaced = scope in ('all', 'included')
        include_exclusions = scope in ('all', 'excluded')

        passed_statuses = {'accepted', 'full_text_passed', 'abstract_passed'}
        excluded_statuses = {'rejected', 'withdrawn'}

        if scope == 'included':
            target_statuses = list(passed_statuses)
        elif scope == 'excluded':
            target_statuses = list(excluded_statuses)
        else:
            target_statuses = ['accepted', 'full_text_passed', 'abstract_passed', 'rejected', 'withdrawn']

        # Pagination & Filtering handling
        min_score_param = request.query_params.get('min_score') or request.query_params.get('score')
        min_score = None
        if min_score_param is not None and str(min_score_param).strip() != '':
            try:
                min_score = float(min_score_param)
            except (ValueError, TypeError):
                min_score = None

        sort_param = (
            request.query_params.get('sort')
            or request.query_params.get('ordering')
            or ''
        ).strip().lower()

        page_param = request.query_params.get('page')
        page_size_param = request.query_params.get('page_size') or request.query_params.get('pageSize')
        is_paginated = page_param is not None or page_size_param is not None

        if is_paginated:
            try:
                page = max(1, int(page_param)) if page_param is not None else 1
            except (ValueError, TypeError):
                page = 1
            try:
                page_size = max(1, min(200, int(page_size_param))) if page_size_param is not None else 20
            except (ValueError, TypeError):
                page_size = 20
        else:
            page = 1
            page_size = None

        from django.db import models as db_models
        base_pm_qs = PaperMetric.objects.filter(pipeline_run=run)
        definitions = list(workspace.extraction_definitions.filter(is_active=True).order_by('order', 'created_at'))
        definitions_metadata = [
            {
                "id": str(d.id),
                "key": d.name.lower().replace(' ', '_').replace('-', '_'),
                "name": d.name,
                "order": getattr(d, 'order', 0),
                "is_trl": 'trl' in d.name.lower() or 'technology readiness' in d.name.lower(),
            }
            for d in definitions
        ]

        import math
        paged_surfaced_scored = None

        if is_paginated and page_size is not None:
            # Paginated path: slice directly in PostgreSQL to avoid fetching hundreds of Paper models into memory
            start = (page - 1) * page_size
            end = start + page_size

            if include_surfaced:
                surfaced_qs = (
                    base_pm_qs.filter(screening_status__in=passed_statuses, paper__isnull=False)
                    .defer('metrics_data')
                )
                if min_score is not None and min_score > 0:
                    surfaced_qs = surfaced_qs.filter(signal_score__gte=min_score)

                if sort_param.startswith('dim:'):
                    target_dim_key = sort_param[4:].strip().lower()
                    all_surfaced_metrics = list(
                        surfaced_qs.select_related('paper')
                        .order_by(db_models.F('signal_score').desc(nulls_last=True), '-created_at')
                    )
                    total_surfaced = len(all_surfaced_metrics)

                    surfaced_paper_ids = [pm.paper_id for pm in all_surfaced_metrics if pm.paper_id]
                    extractions_map = {}
                    if surfaced_paper_ids:
                        from research_intelligence.models import Extraction
                        exts = list(
                            Extraction.objects.filter(paper_id__in=surfaced_paper_ids)
                            .select_related('extraction_definition')
                            .order_by('-created_at')
                        )
                        for ext in exts:
                            extractions_map.setdefault(ext.paper_id, []).append(ext)

                    from research_intelligence.services.scorecard_service import build_single_scored_paper

                    all_scored = []
                    for pm in all_surfaced_metrics:
                        sp = build_single_scored_paper(
                            paper=pm.paper,
                            definitions=definitions,
                            target_pr_id=run.id,
                            target_pr=run,
                            metrics_list=[pm],
                            extractions_list=extractions_map.get(pm.paper.id, []),
                            request=request,
                        )
                        sp['screening_status'] = pm.screening_status
                        sp['signal_score'] = pm.signal_score
                        all_scored.append(sp)

                    def _dim_val(sp):
                        for d in sp.get('dimensions', []):
                            if d.get('key') == target_dim_key:
                                v = d.get('value')
                                if isinstance(v, (int, float)):
                                    return v
                        return -float('inf')

                    all_scored.sort(
                        key=lambda sp: (_dim_val(sp), sp.get('signal_score') or 0.0),
                        reverse=True
                    )
                    paged_surfaced_scored = all_scored[start:end]
                    paged_surfaced_metrics = []
                else:
                    if sort_param in ('published', 'date', '-published', '-date'):
                        order_expr = (db_models.F('paper__created_at').desc(nulls_last=True), '-created_at')
                    elif sort_param in ('score_asc', '+score', 'signal_score_asc'):
                        order_expr = (db_models.F('signal_score').asc(nulls_last=True), '-created_at')
                    else:
                        order_expr = (db_models.F('signal_score').desc(nulls_last=True), '-created_at')

                    paged_surfaced_metrics = list(
                        surfaced_qs.select_related('paper').order_by(*order_expr)[start:end]
                    )
                    if start == 0 and len(paged_surfaced_metrics) < page_size:
                        total_surfaced = len(paged_surfaced_metrics)
                    else:
                        total_surfaced = surfaced_qs.count()
            else:
                total_surfaced = 0
                paged_surfaced_metrics = []

            if include_exclusions:
                excluded_qs = (
                    base_pm_qs.filter(screening_status__in=excluded_statuses, paper__isnull=False)
                    .defer('metrics_data')
                )
                if scope == 'excluded':
                    paged_excluded_metrics = list(
                        excluded_qs.select_related('paper')
                        .order_by(db_models.F('signal_score').desc(nulls_last=True), '-created_at')[start:end]
                    )
                    if start == 0 and len(paged_excluded_metrics) < page_size:
                        total_exclusions = len(paged_excluded_metrics)
                    else:
                        total_exclusions = excluded_qs.count()
                else:
                    paged_excluded_metrics = list(
                        excluded_qs.select_related('paper')
                        .order_by(db_models.F('signal_score').desc(nulls_last=True), '-created_at')
                    )
                    total_exclusions = len(paged_excluded_metrics)
            else:
                total_exclusions = 0
                paged_excluded_metrics = []

            total_items = total_exclusions if scope == 'excluded' else total_surfaced
            total_pages = max(1, math.ceil(total_items / page_size)) if page_size > 0 else 1
        else:
            # Unpaginated backward-compatibility path: single combined query to preserve 1-query contract
            unpaginated_qs = base_pm_qs.filter(
                screening_status__in=target_statuses,
                paper__isnull=False
            ).defer('metrics_data')
            if min_score is not None and min_score > 0:
                unpaginated_qs = unpaginated_qs.filter(
                    db_models.Q(screening_status__in=excluded_statuses) |
                    (db_models.Q(screening_status__in=passed_statuses) & db_models.Q(signal_score__gte=min_score))
                )

            if sort_param in ('published', 'date', '-published', '-date'):
                unpaginated_order = (db_models.F('paper__created_at').desc(nulls_last=True), '-created_at')
            elif sort_param in ('score_asc', '+score', 'signal_score_asc'):
                unpaginated_order = (db_models.F('signal_score').asc(nulls_last=True), '-created_at')
            else:
                unpaginated_order = (db_models.F('signal_score').desc(nulls_last=True), '-created_at')

            all_metrics = list(
                unpaginated_qs.select_related('paper').order_by(*unpaginated_order)
            )
            surfaced_metrics = []
            paged_excluded_metrics = []
            for pm in all_metrics:
                if pm.screening_status in passed_statuses:
                    if include_surfaced:
                        surfaced_metrics.append(pm)
                else:
                    if include_exclusions:
                        paged_excluded_metrics.append(pm)

            paged_surfaced_metrics = surfaced_metrics
            total_surfaced = len(surfaced_metrics)
            total_exclusions = len(paged_excluded_metrics)
            total_items = total_exclusions if scope == 'excluded' else total_surfaced
            total_pages = 1
            page_size = total_items

        exclusions = []
        if include_exclusions and paged_excluded_metrics:
            from research_intelligence.utils.source_url import resolve_paper_source_url
            for pm in paged_excluded_metrics:
                reason = pm.screening_reasoning or pm.abstract_screening_reasoning or pm.full_text_screening_reasoning
                meta = getattr(pm.paper, 'meta', None) or {}
                pub_date = None
                for k in ('published', 'publication_date', 'published_date', 'date'):
                    val = meta.get(k)
                    if val:
                        pub_date = str(val)[:10]
                        break
                if not pub_date and pm.paper.created_at:
                    pub_date = pm.paper.created_at.strftime('%Y-%m-%d')

                source_url = resolve_paper_source_url(pm.paper)

                exclusions.append({
                    "paper_id": str(pm.paper.id),
                    "title": pm.paper.title,
                    "source": pm.paper.source_database or 'arXiv',
                    "reason": reason,
                    "published_date": pub_date,
                    "source_url": source_url,
                })

        surfaced = []
        if paged_surfaced_scored is not None:
            surfaced = paged_surfaced_scored
        elif include_surfaced and paged_surfaced_metrics:
            surfaced_paper_ids = [pm.paper_id for pm in paged_surfaced_metrics if pm.paper_id]

            extractions_map = {}
            if surfaced_paper_ids:
                from research_intelligence.models import Extraction
                exts = list(
                    Extraction.objects.filter(paper_id__in=surfaced_paper_ids)
                    .select_related('extraction_definition')
                    .order_by('-created_at')
                )
                for ext in exts:
                    extractions_map.setdefault(ext.paper_id, []).append(ext)

            from research_intelligence.services.scorecard_service import build_single_scored_paper

            for pm in paged_surfaced_metrics:
                sp = build_single_scored_paper(
                    paper=pm.paper,
                    definitions=definitions,
                    target_pr_id=run.id,
                    target_pr=run,
                    metrics_list=[pm],
                    extractions_list=extractions_map.get(pm.paper.id, []),
                    request=request,
                )
                sp['screening_status'] = pm.screening_status
                sp['signal_score'] = pm.signal_score
                surfaced.append(sp)

        run_dt = run.completed_at or run.run_date or run.started_at
        actual_date_str = run_dt.strftime('%Y-%m-%d')

        passed_count = (
            run.total_papers_passed_screening
            if run.total_papers_passed_screening is not None
            else total_surfaced
        )
        total_fetched = run.total_papers_fetched or (
            passed_count + (total_exclusions if include_exclusions else 0)
        )
        surfaced_count = passed_count

        in_brief_text = (
            run.status_message
            or f"{workspace.name} briefing for {actual_date_str}: {total_fetched} papers ingested, {surfaced_count} surfaced."
        )

        return Response({
            "run_id": str(run.id),
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "date": actual_date_str,
            "title": f"{workspace.name} Briefing — {actual_date_str}",
            "in_brief": in_brief_text,
            "in_brief_source": "template",
            "funnel": {
                "fetched": total_fetched,
                "passed_screening": passed_count,
                "surfaced": surfaced_count,
            },
            "total": total_items,
            "total_papers": total_surfaced,
            "total_exclusions": total_exclusions,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "papers": surfaced,
            "exclusions": exclusions,
            "definitions": definitions_metadata,
            "generated_at": (
                run.completed_at.isoformat()
                if (hasattr(run.completed_at, 'tzinfo') and run.completed_at.tzinfo)
                else (run.completed_at.isoformat() + "Z")
            ) if run.completed_at else None,
        })

    @extend_schema(
        tags=['Workspaces Management', 'Settings & Preferences'],
        description="Get or set notification and email digest preferences for the current user in this workspace.",
        responses={
            200: OpenApiResponse(description="User workspace notification and email digest preferences (e.g. {'digest_email': true})"),
        }
    )
    @action(detail=True, methods=['get', 'put'], url_path='preferences')
    def preferences(self, request, pk=None):
        workspace = self.get_object()
        user = request.user
        from research_intelligence.models import Subscriber
        if request.method == 'GET':
            user_email = user.email or ''
            has_sub = False
            if user_email:
                has_sub = Subscriber.objects.filter(
                    workspace=workspace,
                    email__iexact=user_email,
                    is_active=True
                ).exists()
            return Response({"digest_email": has_sub})

        # PUT
        digest_email = bool(request.data.get('digest_email', True))
        user_email = (user.email or '').strip()
        if not user_email:
            return Response({"digest_email": False})

        if digest_email:
            Subscriber.objects.update_or_create(
                workspace=workspace,
                email=user_email,
                defaults={
                    'is_active': True,
                    'name': user.get_full_name() or user.username,
                    'subscription_type': 'result_report',
                }
            )
        else:
            Subscriber.objects.filter(
                workspace=workspace,
                email__iexact=user_email
            ).update(is_active=False)

        return Response({"digest_email": digest_email})



@extend_schema(tags=['Extraction Definitions'])
class ExtractionDefinitionViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for dynamic Extraction Definitions within a workspace.
    """
    queryset = ExtractionDefinition.objects.none()
    serializer_class = ExtractionDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['order', 'created_at', 'name', 'version', 'is_active']
    ordering = ['order', 'created_at']

    def get_queryset(self):
        user = self.request.user
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        qs = ExtractionDefinition.objects.filter(workspace_id__in=user_ws_ids).order_by('order', 'created_at')
        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)
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
            raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=obj.workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        has_access = WorkspaceMember.objects.filter(
            workspace=instance.workspace, user=user, role__in=['admin', 'manager']
        ).exists()
        if not has_access:
            raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        instance.delete()

