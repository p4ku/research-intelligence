import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from research_intelligence.models import WorkflowSchedule, WorkspaceMember
from research_intelligence.services import check_workspace_access
from ..serializers.schedules import WorkflowScheduleSerializer

logger = logging.getLogger(__name__)


@extend_schema(tags=['Workflow Schedules'])
class WorkflowScheduleViewSet(viewsets.ModelViewSet):
    """
    REST API ViewSet for automated Workflow Schedule management (Cron & Periodic jobs).
    Allows setting daily, weekdays, weekly, monthly, and custom cron recurring executions.
    """
    serializer_class = WorkflowScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-is_active', 'next_run_at', '-created_at']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return WorkflowSchedule.objects.none()

        if getattr(user, 'is_superuser', False):
            qs = WorkflowSchedule.objects.select_related('workspace', 'created_by', 'last_pipeline_run').all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = WorkflowSchedule.objects.select_related('workspace', 'created_by', 'last_pipeline_run').filter(
                workspace_id__in=user_ws_ids
            )

        workspace_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            qs = qs.filter(is_active=is_active_param.lower() in ('true', '1'))

        return qs

    def perform_create(self, serializer):
        workspace = serializer.validated_data.get('workspace')
        workspace_obj, _, error = check_workspace_access(
            self.request.user, str(workspace.id), required_roles=['admin', 'manager']
        )
        if error:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(error)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        workspace = serializer.instance.workspace
        _, _, error = check_workspace_access(
            self.request.user, str(workspace.id), required_roles=['admin', 'manager']
        )
        if error:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(error)
        serializer.save()

    def perform_destroy(self, instance):
        _, _, error = check_workspace_access(
            self.request.user, str(instance.workspace.id), required_roles=['admin', 'manager']
        )
        if error:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(error)
        instance.delete()

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Schedule triggered successfully"),
            403: OpenApiResponse(description="Forbidden - Requires Admin/Manager role"),
        }
    )
    @action(detail=True, methods=['post'])
    def trigger(self, request, pk=None):
        """Manually triggers this scheduled workflow immediately."""
        schedule = self.get_object()
        _, _, error = check_workspace_access(
            request.user, str(schedule.workspace.id), required_roles=['admin', 'manager', 'researcher']
        )
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        agent = schedule.trigger_run(triggered_by_user=request.user)
        return Response({
            "message": f"Successfully triggered scheduled workflow '{schedule.name}'.",
            "agent_id": str(agent.id),
            "pipeline_run_id": str(schedule.last_pipeline_run.id) if schedule.last_pipeline_run else None,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
        }, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Schedule active status toggled"),
            403: OpenApiResponse(description="Forbidden"),
        }
    )
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggles the schedule between active and paused states."""
        schedule = self.get_object()
        _, _, error = check_workspace_access(
            request.user, str(schedule.workspace.id), required_roles=['admin', 'manager']
        )
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        schedule.is_active = not schedule.is_active
        if schedule.is_active:
            schedule.next_run_at = schedule.compute_next_run()
        else:
            schedule.next_run_at = None
        schedule.save(update_fields=['is_active', 'next_run_at'])

        return Response(WorkflowScheduleSerializer(schedule).data, status=status.HTTP_200_OK)
