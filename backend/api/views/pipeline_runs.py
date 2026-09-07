import json
import uuid
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from research_intelligence.models import (
    PipelineRun,
    ComponentRun,
    Workspace,
    WorkspaceMember,
)
from ..serializers.pipeline_runs import (
    PipelineRunSerializer,
    PipelineRunDetailSerializer,
    ComponentRunSerializer,
    TriggerStepSerializer,
    CreatePipelineRunSerializer,
    StartPipelineRunSerializer,
)
from ..pagination import StandardResultsSetPagination
from mcp_server.tools.pipeline_runs.triggers import (
    start_pipeline_run_logic,
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    trigger_signal_score_job_logic,
    trigger_reporting_job_logic,
)
from mcp_server.tools.pipeline_runs.lifecycle import (
    abort_job_logic,
    delete_pipeline_run_logic,
)
from research_intelligence.services import check_workspace_access


@extend_schema(tags=['Pipeline Runs & Components'])
class PipelineRunViewSet(viewsets.ModelViewSet):
    """
    REST API ViewSet for SLR Pipeline Runs lifecycle, execution status, and step triggers.
    Scoped strictly to workspaces the authenticated user belongs to.
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    ordering_fields = ['started_at', 'completed_at', 'status', 'current_stage', 'tokens_consumed', 'usd_cost']
    ordering = ['-started_at']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PipelineRunDetailSerializer
        if self.action == 'create':
            return CreatePipelineRunSerializer
        if self.action == 'start':
            return StartPipelineRunSerializer
        if self.action == 'trigger_step':
            return TriggerStepSerializer
        return PipelineRunSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return PipelineRun.objects.none()

        if getattr(user, 'is_superuser', False):
            qs = PipelineRun.objects.select_related('workspace', 'triggered_by', 'schedule').all().order_by('-started_at')
        else:
            user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
            if not user_ws_ids:
                return PipelineRun.objects.none()
            qs = PipelineRun.objects.select_related('workspace', 'triggered_by', 'schedule').filter(
                workspace_id__in=user_ws_ids
            ).order_by('-started_at')

        if getattr(self, 'action', None) == 'retrieve':
            qs = qs.prefetch_related('component_runs')

        workspace_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if workspace_id:
            if str(workspace_id).lower() in ('undefined', 'null', ''):
                return qs.none()
            import uuid
            try:
                ws_uuid = uuid.UUID(str(workspace_id))
                qs = qs.filter(workspace_id=ws_uuid)
            except (ValueError, TypeError):
                return qs.none()

        domain = self.request.query_params.get('domain') or self.request.query_params.get('workspace_name')
        if domain and str(domain).lower() not in ('all', 'undefined', 'null', ''):
            qs = qs.filter(workspace__name__iexact=domain.strip())

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    @extend_schema(
        request=CreatePipelineRunSerializer,
        responses={
            201: PipelineRunSerializer,
            400: OpenApiResponse(description="Bad request - missing workspace ID or invalid payload"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions in target workspace"),
        }
    )
    def create(self, request, *args, **kwargs):
        serializer = CreatePipelineRunSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        workspace_id = str(serializer.validated_data['workspace_id'])
        reprocess_existing = serializer.validated_data.get('reprocess_existing', False)
        run_name = serializer.validated_data.get('name') or "SLR Review Run"
        start_date = serializer.validated_data.get('start_date')
        end_date = serializer.validated_data.get('end_date')
        n_last_days = serializer.validated_data.get('n_last_days')

        workspace, membership, error = check_workspace_access(
            request.user, workspace_id, required_roles=['admin', 'manager', 'researcher']
        )
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        config_override = {}
        if start_date:
            config_override['start_date'] = start_date
        if end_date:
            config_override['end_date'] = end_date
        if n_last_days is not None:
            config_override['n_last_days'] = n_last_days

        pipeline_run = PipelineRun.objects.create(
            workspace=workspace,
            name=run_name,
            status='pending',
            current_stage='search',
            reprocess_existing=reprocess_existing,
            triggered_by=request.user,
            configuration_override=config_override,
        )

        return Response(
            PipelineRunSerializer(pipeline_run).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=StartPipelineRunSerializer,
        responses={
            201: OpenApiResponse(description="Autonomous pipeline run started successfully"),
            400: OpenApiResponse(description="Bad request or validation error"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
        }
    )
    @action(detail=False, methods=['post'], url_path='start')
    def start(self, request, *args, **kwargs):
        serializer = StartPipelineRunSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        n_last_days = data.get('n_last_days')
        res_json = start_pipeline_run_logic(
            user=request.user,
            workspace_id=str(data['workspace_id']),
            name=data.get('name'),
            limit=data.get('limit'),
            query_prefix=data.get('query_prefix'),
            skip_abstract_screening=data.get('skip_abstract_screening'),
            notification_email=data.get('notification_email'),
            reprocess_existing=data.get('reprocess_existing'),
            autonomous=data.get('autonomous', True),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
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
        responses={
            200: OpenApiResponse(description="Pipeline run and stored files purged successfully"),
            403: OpenApiResponse(description="Forbidden - requires Admin role in workspace"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        res_json = delete_pipeline_run_logic(user=request.user, pipeline_run_id=str(instance.id))
        try:
            res_data = json.loads(res_json)
            if res_data.get("status") == "success" or res_data.get("success") is True:
                return Response(res_data, status=status.HTTP_200_OK)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            if "Error:" in res_json or "denied" in res_json.lower() or "forbidden" in res_json.lower():
                return Response({"error": res_json}, status=status.HTTP_403_FORBIDDEN)
            return Response({"message": res_json}, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Pipeline run successfully aborted"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'])
    def abort(self, request, pk=None):
        instance = self.get_object()
        res_json = abort_job_logic(user=request.user, pipeline_run_id=str(instance.id))
        try:
            res_data = json.loads(res_json)
            if not res_data.get("success", False):
                return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
            return Response(res_data, status=status.HTTP_200_OK)
        except Exception:
            if "Error:" in res_json:
                return Response({"error": res_json}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"message": res_json}, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Pipeline run successfully paused"),
            400: OpenApiResponse(description="Pipeline run cannot be paused"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        instance = self.get_object()
        reason = request.data.get('reason', 'Paused via API')
        ok = instance.pause(reason=reason)
        if not ok:
            return Response(
                {"success": False, "error": f"Cannot pause run in status '{instance.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response({
            "success": True,
            "pipeline_run_id": str(instance.id),
            "status": instance.status,
            "message": f"Pipeline run paused: {reason}"
        }, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Pipeline run successfully resumed"),
            400: OpenApiResponse(description="Pipeline run cannot be resumed"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        instance = self.get_object()
        ok = instance.resume()
        if not ok:
            return Response(
                {"success": False, "error": f"Cannot resume run in status '{instance.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response({
            "success": True,
            "pipeline_run_id": str(instance.id),
            "status": instance.status,
            "message": "Pipeline run resumed and tick scheduled"
        }, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Pipeline run tick executed"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'])
    def tick(self, request, pk=None):
        instance = self.get_object()
        res = instance.tick()
        http_status = status.HTTP_200_OK if res.get("success", False) else status.HTTP_400_BAD_REQUEST
        return Response(res, status=http_status)

    @extend_schema(
        parameters=[
            OpenApiParameter(name="step_name", type=str, location=OpenApiParameter.QUERY, required=False,
                             description="Step to rerun from ('search', 'download', 'ocr', 'abstract_screening', 'full_text_screening', 'extraction', 'signal_score', 'reporting'). If omitted, automatically resumes from the failed step."),
        ],
        responses={
            200: OpenApiResponse(description="Pipeline rerun successfully initiated"),
            400: OpenApiResponse(description="Invalid step or cannot rerun"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'], url_path='rerun-from-step')
    def rerun_from_step(self, request, pk=None):
        instance = self.get_object()
        step_name = request.data.get('step_name') or request.query_params.get('step_name')
        from mcp_server.tools.pipeline_runs import rerun_pipeline_from_step_logic
        res_json = rerun_pipeline_from_step_logic(user=request.user, pipeline_run_id=str(instance.id), step_name=step_name)
        res_data = json.loads(res_json)
        if res_data.get("status") == "error":
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
        return Response(res_data, status=status.HTTP_200_OK)

    @extend_schema(
        request=TriggerStepSerializer,
        responses={
            200: OpenApiResponse(description="Pipeline step successfully launched"),
            400: OpenApiResponse(description="Bad request or missing prerequisite step data"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['post'], url_path='trigger-step')
    def trigger_step(self, request, pk=None):
        pipeline_run = self.get_object()
        serializer = TriggerStepSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        step_type = serializer.validated_data['step_type']
        limit = serializer.validated_data.get('limit', 50)
        skip_abstract = serializer.validated_data.get('skip_abstract_screening', False)
        stage_param = serializer.validated_data.get('stage')
        query_prefix = serializer.validated_data.get('query_prefix')

        user = request.user
        pr_id = str(pipeline_run.id)
        ws_id = str(pipeline_run.workspace_id)

        if step_type == 'search':
            n_last_days = serializer.validated_data.get('n_last_days')
            res_json = trigger_search_job_logic(
                user=user,
                workspace_id=ws_id,
                limit=limit,
                reprocess_existing=pipeline_run.reprocess_existing,
                query_prefix=query_prefix,
                start_date=serializer.validated_data.get('start_date'),
                end_date=serializer.validated_data.get('end_date'),
                n_last_days=n_last_days,
            )
        elif step_type == 'download':
            res_json = trigger_pdf_download_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
            )
        elif step_type == 'ocr':
            res_json = trigger_ocr_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
            )
        elif step_type in ('screening', 'abstract_screening', 'full_text_screening'):
            if step_type == 'abstract_screening':
                stage = 'abstract'
            elif step_type == 'full_text_screening':
                stage = 'full_text'
            else:
                stage = stage_param or ('full_text' if skip_abstract else 'abstract')
            res_json = trigger_screening_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
                stage=stage,
            )
        elif step_type == 'extraction':
            res_json = trigger_extraction_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
            )
        elif step_type == 'signal_score':
            res_json = trigger_signal_score_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
            )
        elif step_type == 'reporting':
            res_json = trigger_reporting_job_logic(
                user=user,
                pipeline_run_id=pr_id,
            )
        else:
            return Response({"error": f"Unsupported step_type '{step_type}'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            res_data = json.loads(res_json)
            if res_data.get("success") is False or "error" in res_data:
                return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
            return Response(res_data, status=status.HTTP_200_OK)
        except Exception:
            if "Error:" in res_json:
                return Response({"error": res_json}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"message": res_json}, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: ComponentRunSerializer(many=True),
            404: OpenApiResponse(description="Pipeline run not found"),
        }
    )
    @action(detail=True, methods=['get'])
    def components(self, request, pk=None):
        pipeline_run = self.get_object()
        component_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at')
        return Response(ComponentRunSerializer(component_runs, many=True).data, status=status.HTTP_200_OK)


@extend_schema(tags=['Pipeline Runs & Components'])
class ComponentRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    REST API ReadOnly ViewSet for Component Runs telemetry, step logs, execution timings, and error metrics.
    Scoped strictly to workspaces the authenticated user belongs to.
    """
    serializer_class = ComponentRunSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['started_at', 'completed_at', 'step_type', 'component_name', 'status']
    ordering = ['-started_at']

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return ComponentRun.objects.none()

        if getattr(user, 'is_superuser', False):
            qs = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').all().order_by('-started_at')
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').filter(
                pipeline_run__workspace_id__in=user_ws_ids
            ).order_by('-started_at')

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id and str(ws_id).lower() not in ('undefined', 'null', ''):
            import uuid
            try:
                ws_uuid = uuid.UUID(str(ws_id))
                qs = qs.filter(pipeline_run__workspace_id=ws_uuid)
            except (ValueError, TypeError):
                return qs.none()

        pipeline_run_id = self.request.query_params.get('pipeline_run') or self.request.query_params.get('pipeline_run_id')
        if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
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
                    qs = qs.filter(pipeline_run_id=latest_run.id)
                else:
                    return qs.none()
            else:
                import uuid
                try:
                    pr_uuid = uuid.UUID(str(pipeline_run_id))
                    qs = qs.filter(pipeline_run_id=pr_uuid)
                except (ValueError, TypeError):
                    return qs.none()

        step_type = self.request.query_params.get('step_type')
        if step_type:
            qs = qs.filter(step_type=step_type)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Component run successfully aborted"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Component run not found"),
        }
    )
    @action(detail=True, methods=['post'])
    def abort(self, request, pk=None):
        instance = self.get_object()
        res_json = abort_job_logic(user=request.user, component_run_id=str(instance.id))
        try:
            res_data = json.loads(res_json)
            if not res_data.get("success", False):
                return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
            return Response(res_data, status=status.HTTP_200_OK)
        except Exception:
            if "Error:" in res_json:
                return Response({"error": res_json}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"message": res_json}, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Component task successfully re-dispatched on Celery"),
            400: OpenApiResponse(description="Failed to re-execute component"),
            403: OpenApiResponse(description="Forbidden - requires Admin or Manager role"),
            404: OpenApiResponse(description="Component run not found"),
        }
    )
    @action(detail=True, methods=['post'], url_path='reexecute')
    def reexecute(self, request, pk=None):
        instance = self.get_object()
        from mcp_server.tools.pipeline_runs import reexecute_component_run_logic
        res_json = reexecute_component_run_logic(user=request.user, component_run_id=str(instance.id))
        res_data = json.loads(res_json)
        if res_data.get("status") == "error":
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
        return Response(res_data, status=status.HTTP_200_OK)
