from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from research_intelligence.models import Subscriber, WorkspaceMember
from ..serializers.workspaces import SubscriberSerializer


@extend_schema(tags=['Subscribers Management'])
class SubscriberViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace Subscribers (email notifications and report recipients).
    Accessible only to members of the workspace.
    """
    serializer_class = SubscriberSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'email', 'subscription_type', 'is_active']
    ordering = ['-created_at']

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from research_intelligence.features import is_feature_enabled, Feature
        from rest_framework.exceptions import NotFound
        if not is_feature_enabled(Feature.EMAIL_NOTIFICATIONS):
            raise NotFound("Email subscribers feature is currently disabled.")

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            qs = Subscriber.objects.all().order_by('-created_at')
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = Subscriber.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(workspace_id=ws_id)
        sub_type = self.request.query_params.get('subscription_type')
        if sub_type:
            qs = qs.filter(subscription_type=sub_type)
        return qs

    def perform_create(self, serializer):
        workspace = serializer.validated_data.get('workspace')
        if not workspace:
            raise PermissionDenied("Workspace is required.")
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage subscribers in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        subscriber = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=subscriber.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage subscribers in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage subscribers in this workspace.")
        instance.delete()
