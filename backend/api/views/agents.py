import json
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from research_intelligence.models import ResearchAgentProcess, WorkspaceMember
from ..serializers.agents import (
    ResearchAgentProcessSerializer,
    StartResearchAgentSerializer,
)
from mcp_server.tools.agents import (
    start_research_agent_logic,
    get_research_agent_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic
)
from drf_spectacular.utils import extend_schema, OpenApiResponse


@extend_schema(tags=['Autonomous Agents & Pipelines'])
class ResearchAgentViewSet(viewsets.ModelViewSet):
    """
    REST API ViewSet for autonomous Research Agent Processes.
    Orchestrates the SLR pipeline from Search & Screening to Parameter Extraction and Composite Signal Scoring.
    Scoped strictly to workspaces the authenticated user belongs to.
    """
    queryset = ResearchAgentProcess.objects.none()
    serializer_class = ResearchAgentProcessSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    ordering_fields = ['started_at', 'completed_at', 'name', 'status', 'current_stage']
    ordering = ['-started_at']

    def get_queryset(self):
        user = self.request.user
        user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return ResearchAgentProcess.objects.none()
        qs = ResearchAgentProcess.objects.select_related('workspace').filter(
            workspace_id__in=user_ws_ids
        )
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
        return qs.order_by('-started_at')

    @extend_schema(
        request=StartResearchAgentSerializer,
        responses={
            201: ResearchAgentProcessSerializer,
            400: OpenApiResponse(description="Bad request - missing workspace ID or invalid parameters"),
            403: OpenApiResponse(description="Forbidden - Insufficient permissions in target workspace"),
        },
        summary="Launch autonomous research agent",
        description="Initiates an end-to-end autonomous research state engine run."
    )
    def create(self, request, *args, **kwargs):
        serializer = StartResearchAgentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        workspace_id = validated["workspace_id"]
        name = validated.get("name")
        limit = validated.get("limit", 2000)
        start_date = validated.get("start_date")
        end_date = validated.get("end_date")
        n_last_days = validated.get("n_last_days")
        query_prefix = validated.get("query_prefix")
        skip_abstract = validated.get("skip_abstract_screening")
        notification_email = validated.get("notification_email")
        reprocess_existing = validated.get("reprocess_existing", False)

        res_json = start_research_agent_logic(
            user=request.user,
            workspace_id=str(workspace_id),
            name=name,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            n_last_days=n_last_days,
            query_prefix=query_prefix,
            skip_abstract_screening=skip_abstract,
            notification_email=notification_email,
            reprocess_existing=reprocess_existing
        )
        try:
            res_data = json.loads(res_json)
        except Exception:
            return Response({"result": res_json}, status=status.HTTP_200_OK)

        if "error" in res_data or res_data.get("status") == "error":
            err_msg = str(res_data.get("error", ""))
            if "denied" in err_msg.lower() or "permissions" in err_msg.lower():
                return Response(res_data, status=status.HTTP_403_FORBIDDEN)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)


        process_id = res_data.get("process_id")
        if process_id:
            process = ResearchAgentProcess.objects.get(id=process_id)
            serializer = self.get_serializer(process)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(res_data, status=status.HTTP_200_OK)

    def _parse_mcp_response(self, res_json):
        try:
            return json.loads(res_json)
        except Exception:
            return {"message": str(res_json)}

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Research agent process successfully paused"),
            400: OpenApiResponse(description="Bad request or invalid state transition"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Agent process not found"),
        },
        summary="Pause running research agent",
        description="Temporarily pauses execution after the active step completes."
    )
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        instance = self.get_object()
        res_json = pause_research_agent_logic(request.user, str(instance.id))
        parsed = self._parse_mcp_response(res_json)
        if parsed.get("status") == "error":
            err_msg = str(parsed.get("error", ""))
            status_code = status.HTTP_403_FORBIDDEN if "denied" in err_msg.lower() or "permission" in err_msg.lower() else status.HTTP_400_BAD_REQUEST
            return Response(parsed, status=status_code)
        return Response(parsed)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Research agent process successfully resumed"),
            400: OpenApiResponse(description="Bad request or process not in paused state"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Agent process not found"),
        },
        summary="Resume paused research agent",
        description="Resumes state machine execution from the current pending pipeline step."
    )
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        instance = self.get_object()
        res_json = resume_research_agent_logic(request.user, str(instance.id))
        parsed = self._parse_mcp_response(res_json)
        if parsed.get("status") == "error":
            err_msg = str(parsed.get("error", ""))
            status_code = status.HTTP_403_FORBIDDEN if "denied" in err_msg.lower() or "permission" in err_msg.lower() else status.HTTP_400_BAD_REQUEST
            return Response(parsed, status=status_code)
        return Response(parsed)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Research agent process successfully aborted"),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Agent process not found"),
        },
        summary="Abort running research agent",
        description="Aborts the agent process and terminates running background worker tasks."
    )
    @action(detail=True, methods=['post'])
    def abort(self, request, pk=None):
        instance = self.get_object()
        res_json = abort_research_agent_logic(request.user, str(instance.id))
        parsed = self._parse_mcp_response(res_json)
        if parsed.get("status") == "error":
            err_msg = str(parsed.get("error", ""))
            status_code = status.HTTP_403_FORBIDDEN if "denied" in err_msg.lower() or "permission" in err_msg.lower() else status.HTTP_400_BAD_REQUEST
            return Response(parsed, status=status_code)
        return Response(parsed)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Research agent process and storage purged successfully"),
            403: OpenApiResponse(description="Forbidden - requires Admin role in workspace"),
            404: OpenApiResponse(description="Agent process not found"),
        },
        summary="Purge research agent and files",
        description="Permanently deletes the research agent process, pipeline run, DB records, and run storage directory."
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        res_json = delete_research_agent_logic(request.user, str(instance.id))
        return Response(self._parse_mcp_response(res_json), status=status.HTTP_200_OK)
