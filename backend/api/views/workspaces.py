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
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'monthly_usd_limit']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        base_qs = Workspace.objects.prefetch_related('subscribers', 'scrapers', 'extraction_definitions').order_by('-created_at')
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
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY, description='Page number'),
            OpenApiParameter(name='page_size', type=int, location=OpenApiParameter.QUERY, description='Page size'),
        ],
        description="Dynamic Workspace Scorecard containing all evaluated papers with run-scoped metrics and rich dimension details.",
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
        }
    )
    @action(detail=True, methods=['post'], url_path='run-pipeline')
    def run_pipeline(self, request, pk=None):
        import json
        from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic

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
            err_msg = res_data.get("error", "Error starting pipeline run")
            if "denied" in err_msg.lower() or "permissions" in err_msg.lower():
                return Response(res_data, status=status.HTTP_403_FORBIDDEN)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)

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
        tags=['Workspaces Management', 'Briefings & Editions'],
        description="Paginated list of completed briefing editions for this workspace, newest first.",
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
        seen_dates = set()
        deduped_runs = []
        for run in completed_runs:
            d = (run.completed_at or run.run_date or run.started_at).strftime('%Y-%m-%d')
            if d in seen_dates:
                continue
            seen_dates.add(d)
            deduped_runs.append((d, run))

        page_num = request.query_params.get('page', 1)
        page_size = int(request.query_params.get('page_size', 20))
        try:
            page_num = max(1, int(page_num))
        except (ValueError, TypeError):
            page_num = 1

        total_count = len(deduped_runs)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        slice_items = deduped_runs[start_idx:end_idx]

        target_runs = [run for _, run in slice_items]
        from collections import defaultdict
        papers_by_run = defaultdict(list)
        if target_runs:
            passed_pms = (
                PaperMetric.objects.filter(
                    pipeline_run__in=target_runs,
                    screening_status__in=['accepted', 'full_text_passed', 'abstract_passed']
                )
                .select_related('paper')
                .only(
                    'id', 'pipeline_run_id', 'signal_score', 'screening_status', 'created_at',
                    'paper__id', 'paper__title', 'paper__authors', 'paper__source_database'
                )
                .order_by('-signal_score', '-created_at')
            )
            for pm in passed_pms:
                if pm.paper:
                    authors_list = [a.strip() for a in (pm.paper.authors or '').split(',') if a.strip()]
                    papers_by_run[pm.pipeline_run_id].append({
                        "id": str(pm.paper.id),
                        "title": pm.paper.title,
                        "authors": authors_list,
                        "source": pm.paper.source_database or 'arXiv',
                        "signal_score": pm.signal_score,
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
                "generated_at": run.completed_at.isoformat() if run.completed_at else None,
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
        tags=['Workspaces Management', 'Briefings & Editions'],
        description="Detail of one briefing edition by date (YYYY-MM-DD), including screening exclusions.",
    )
    def edition_detail(self, request, workspace_id=None, edition_date=None, **kwargs):
        ws_id = workspace_id or kwargs.get('pk')
        if not ws_id:
            return Response({"error": "Workspace ID required"}, status=status.HTTP_400_BAD_REQUEST)

        self.kwargs['pk'] = ws_id
        workspace = self.get_object()

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

        from django.db.models import Q
        run = (
            PipelineRun.objects.filter(
                Q(workspace=workspace) &
                Q(status='completed') &
                (
                    (Q(completed_at__gte=start_dt) & Q(completed_at__lt=end_dt)) |
                    Q(run_date=target_date)
                )
            )
            .only(
                'id', 'workspace_id', 'completed_at', 'run_date', 'status_message',
                'total_papers_fetched', 'total_papers_passed_screening'
            )
            .order_by('-completed_at', '-id')
            .first()
        )
        if not run:
            return Response({"error": f"No completed briefing edition found for {edition_date}."}, status=status.HTTP_404_NOT_FOUND)

        all_metrics = list(
            PaperMetric.objects.filter(
                pipeline_run=run,
                screening_status__in=['accepted', 'full_text_passed', 'abstract_passed', 'rejected', 'withdrawn']
            )
            .select_related('paper')
            .only(
                'id', 'pipeline_run_id', 'signal_score', 'screening_status', 'created_at',
                'abstract_screening_reasoning', 'full_text_screening_reasoning',
                'paper__id', 'paper__title', 'paper__authors', 'paper__source_database'
            )
            .order_by('-created_at')
        )

        passed_statuses = {'accepted', 'full_text_passed', 'abstract_passed'}
        surfaced_metrics = []
        exclusions = []

        for pm in all_metrics:
            if not pm.paper:
                continue
            if pm.screening_status in passed_statuses:
                surfaced_metrics.append(pm)
            else:
                reason = pm.screening_reasoning or pm.abstract_screening_reasoning or pm.full_text_screening_reasoning
                exclusions.append({
                    "paper_id": str(pm.paper.id),
                    "title": pm.paper.title,
                    "source": pm.paper.source_database or 'arXiv',
                    "reason": reason,
                })

        surfaced_metrics.sort(
            key=lambda m: (m.signal_score is not None, m.signal_score or 0.0, m.created_at or timezone.now()),
            reverse=True
        )

        surfaced = []
        for pm in surfaced_metrics:
            authors_list = [a.strip() for a in (pm.paper.authors or '').split(',') if a.strip()]
            surfaced.append({
                "id": str(pm.paper.id),
                "title": pm.paper.title,
                "authors": authors_list,
                "source": pm.paper.source_database or 'arXiv',
                "signal_score": pm.signal_score,
            })

        d_str = target_date.strftime('%Y-%m-%d')
        in_brief_text = (
            run.status_message
            or f"{workspace.name} briefing for {d_str}: {run.total_papers_fetched} papers ingested, {len(surfaced)} surfaced, {len(exclusions)} excluded."
        )

        return Response({
            "run_id": str(run.id),
            "workspace_id": str(workspace.id),
            "date": d_str,
            "title": f"{workspace.name} Briefing — {d_str}",
            "in_brief": in_brief_text,
            "in_brief_source": "template",
            "funnel": {
                "fetched": run.total_papers_fetched or (len(surfaced) + len(exclusions)),
                "passed_screening": run.total_papers_passed_screening or len(surfaced),
                "surfaced": len(surfaced),
            },
            "papers": surfaced,
            "exclusions": exclusions,
            "generated_at": run.completed_at.isoformat() if run.completed_at else None,
        })

    @extend_schema(
        tags=['Workspaces Management', 'Settings & Preferences'],
        description="Get or set notification and email digest preferences for the current user in this workspace.",
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
    serializer_class = ExtractionDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'version', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        qs = ExtractionDefinition.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')
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

