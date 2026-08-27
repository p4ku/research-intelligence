from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema
from research_intelligence.models import UserActivityLog, WorkspaceMember
from api.serializers.activity_logs import UserActivityLogSerializer


@extend_schema(tags=['Operational Activity Logs'])
class UserActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    REST API endpoint for querying user activity & operational audit logs.
    """
    serializer_class = UserActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return UserActivityLog.objects.none()
        if getattr(user, 'is_superuser', False):
            qs = UserActivityLog.objects.all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = UserActivityLog.objects.filter(workspace_id__in=user_ws_ids) | UserActivityLog.objects.filter(user=user)

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
