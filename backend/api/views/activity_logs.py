from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter
from research_intelligence.models import UserActivityLog, WorkspaceMember
from api.serializers.activity_logs import UserActivityLogSerializer
from ..pagination import StandardResultsSetPagination


@extend_schema(
    tags=['Operational Activity Logs'],
    parameters=[
        OpenApiParameter(name='workspace', type=str, location=OpenApiParameter.QUERY, description='Filter audit logs by workspace UUID'),
        OpenApiParameter(name='interface', type=str, location=OpenApiParameter.QUERY, description='Filter by interface (e.g. rest_api, fastmcp, cli)'),
        OpenApiParameter(name='status', type=str, location=OpenApiParameter.QUERY, description='Filter by status (success, unauthorized, failed)'),
    ]
)
class UserActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    REST API ReadOnly endpoint for querying user activity & operational audit logs.
    Read-only: audit logs are strictly immutable and recorded automatically by system middleware.
    """
    serializer_class = UserActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'head', 'options']
    ordering_fields = ['timestamp', 'action_name', 'status', 'execution_time_ms', 'interface']
    ordering = ['-timestamp']

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return UserActivityLog.objects.none()
        base_qs = UserActivityLog.objects.select_related('user', 'workspace')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all().order_by('-timestamp')
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = (base_qs.filter(workspace_id__in=user_ws_ids) | base_qs.filter(user=user)).order_by('-timestamp')

        workspace_id = self.request.query_params.get('workspace')
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)

        interface = self.request.query_params.get('interface')
        if interface:
            qs = qs.filter(interface=interface)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs.distinct()
