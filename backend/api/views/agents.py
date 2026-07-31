import json
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from research_intelligence.models import ResearchAgentProcess
from ..serializers.agents import ResearchAgentProcessSerializer
from research_intelligence.mcp.tools.agent_processes import (
    start_research_agent_logic,
    get_research_agent_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic
)


class ResearchAgentViewSet(viewsets.ModelViewSet):
    """
    REST API ViewSet for autonomous Research Agent Processes:
    - GET /api/agents/ : List agent processes
    - POST /api/agents/ : Start a new agent process
    - GET /api/agents/{id}/ : Retrieve status & step history
    - POST /api/agents/{id}/pause/ : Pause process
    - POST /api/agents/{id}/resume/ : Resume process
    - POST /api/agents/{id}/abort/ : Abort process
    - DELETE /api/agents/{id}/ : Delete process & cleanup
    """
    queryset = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').all().order_by('-started_at')
    serializer_class = ResearchAgentProcessSerializer

    def create(self, request, *args, **kwargs):
        workspace_id = request.data.get("workspace") or request.data.get("workspace_id")
        if not workspace_id:
            return Response({"error": "Must provide 'workspace' ID."}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get("name")
        limit = int(request.data.get("limit", 50))
        date_range_days = request.data.get("date_range_days")
        if date_range_days:
            date_range_days = int(date_range_days)
        query_prefix = request.data.get("query_prefix")
        skip_abstract = request.data.get("skip_abstract_screening")
        notification_email = request.data.get("notification_email")

        res_json = start_research_agent_logic(
            user=request.user,
            workspace_id=str(workspace_id),
            name=name,
            limit=limit,
            date_range_days=date_range_days,
            query_prefix=query_prefix,
            skip_abstract_screening=skip_abstract,
            notification_email=notification_email
        )
        try:
            res_data = json.loads(res_json)
        except Exception:
            return Response({"result": res_json}, status=status.HTTP_200_OK)

        if "error" in res_data or res_data.get("status") == "error":
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)

        process_id = res_data.get("process_id")
        if process_id:
            process = ResearchAgentProcess.objects.get(id=process_id)
            serializer = self.get_serializer(process)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(res_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        res_json = pause_research_agent_logic(request.user, str(pk))
        return Response(json.loads(res_json))

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        res_json = resume_research_agent_logic(request.user, str(pk))
        return Response(json.loads(res_json))

    @action(detail=True, methods=['post'])
    def abort(self, request, pk=None):
        res_json = abort_research_agent_logic(request.user, str(pk))
        return Response(json.loads(res_json))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        res_json = delete_research_agent_logic(request.user, str(instance.id))
        return Response(json.loads(res_json), status=status.HTTP_200_OK)
