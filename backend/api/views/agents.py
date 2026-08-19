import json
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from research_intelligence.models import ResearchAgentProcess, WorkspaceMember
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
    REST API ViewSet for autonomous Research Agent Processes.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = ResearchAgentProcessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').all().order_by('-started_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').filter(
            workspace_id__in=user_ws_ids
        ).order_by('-started_at')

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

    def _parse_mcp_response(self, res_json):
        try:
            return json.loads(res_json)
        except Exception:
            return {"message": str(res_json)}

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        res_json = pause_research_agent_logic(request.user, str(pk))
        return Response(self._parse_mcp_response(res_json))

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        res_json = resume_research_agent_logic(request.user, str(pk))
        return Response(self._parse_mcp_response(res_json))

    @action(detail=True, methods=['post'])
    def abort(self, request, pk=None):
        res_json = abort_research_agent_logic(request.user, str(pk))
        return Response(self._parse_mcp_response(res_json))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        res_json = delete_research_agent_logic(request.user, str(instance.id))
        return Response(self._parse_mcp_response(res_json), status=status.HTTP_200_OK)
