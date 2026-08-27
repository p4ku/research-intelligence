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
    Paper,
    Extraction,
)
from ..serializers.pipeline_runs import (
    PipelineRunSerializer,
    PipelineRunDetailSerializer,
    ComponentRunSerializer,
    TriggerStepSerializer,
    CreatePipelineRunSerializer,
)
from research_intelligence.mcp.tools.pipeline_runs.triggers import (
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
)
from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
from research_intelligence.mcp.tools.pipeline_runs.lifecycle import (
    abort_job_logic,
    delete_pipeline_run_logic,
)
from research_intelligence.mcp.tools.workspaces import _check_workspace_access


@extend_schema(tags=['Pipeline Runs & Components'])
class PipelineRunViewSet(viewsets.ModelViewSet):
    """
    REST API ViewSet for SLR Pipeline Runs lifecycle, execution status, and step triggers.
    Scoped strictly to workspaces the authenticated user belongs to.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PipelineRunDetailSerializer
        if self.action == 'create':
            return CreatePipelineRunSerializer
        if self.action == 'trigger_step':
            return TriggerStepSerializer
        return PipelineRunSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return PipelineRun.objects.none()

        if getattr(user, 'is_superuser', False):
            qs = PipelineRun.objects.select_related('workspace', 'triggered_by').all().order_by('-started_at')
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = PipelineRun.objects.select_related('workspace', 'triggered_by').filter(
                workspace_id__in=user_ws_ids
            ).order_by('-started_at')

        workspace_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)

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

        workspace, membership, error = _check_workspace_access(
            request.user, workspace_id, required_roles=['admin', 'manager', 'researcher']
        )
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        pipeline_run = PipelineRun.objects.create(
            workspace=workspace,
            status='pending',
            current_stage='search',
            reprocess_existing=reprocess_existing,
            triggered_by=request.user,
        )

        return Response(
            PipelineRunSerializer(pipeline_run).data,
            status=status.HTTP_201_CREATED
        )

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

        user = request.user
        pr_id = str(pipeline_run.id)
        ws_id = str(pipeline_run.workspace_id)

        if step_type == 'search':
            res_json = trigger_search_job_logic(
                user=user,
                workspace_id=ws_id,
                limit=limit,
                reprocess_existing=pipeline_run.reprocess_existing,
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
        elif step_type == 'screening':
            res_json = trigger_screening_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
                skip_abstract_screening=skip_abstract,
            )
        elif step_type == 'extraction':
            res_json = trigger_extraction_job_logic(
                user=user,
                pipeline_run_id=pr_id,
                limit=limit,
            )
        elif step_type == 'signal_score':
            comp_run = ComponentRun.objects.create(
                pipeline_run=pipeline_run,
                step_type='signal_score',
                component_name="signal_scorer",
                status='running',
                input_params={"limit": limit, "pipeline_run_id": pr_id}
            )
            try:
                execute_signal_score_job(str(comp_run.id), limit=limit)
                comp_run.refresh_from_db()
                res_json = json.dumps({
                    "success": True,
                    "message": "Signal score evaluation complete.",
                    "component_run_id": str(comp_run.id),
                    "status": comp_run.status,
                })
            except Exception as ex:
                comp_run.status = 'failed'
                comp_run.error_message = str(ex)
                comp_run.save(update_fields=['status', 'error_message'])
                res_json = json.dumps({"success": False, "error": str(ex)})
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

        pipeline_run_id = self.request.query_params.get('pipeline_run') or self.request.query_params.get('pipeline_run_id')
        if pipeline_run_id:
            qs = qs.filter(pipeline_run_id=pipeline_run_id)

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
