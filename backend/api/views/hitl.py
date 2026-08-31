from rest_framework import viewsets, serializers, permissions
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from research_intelligence.models import HITLCorrection, WorkspaceMember


class HITLCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HITLCorrection
        fields = '__all__'


@extend_schema(tags=['Human-in-the-Loop (HITL)'])
class HITLViewSet(viewsets.ModelViewSet):
    """
    Scientists validation overrides (verify, modify, reject).
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = HITLCorrectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['timestamp', 'action']
    ordering = ['-timestamp']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            qs = HITLCorrection.objects.all().order_by('-timestamp')
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = HITLCorrection.objects.filter(extraction__workspace_id__in=user_ws_ids).order_by('-timestamp')

        ws_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if ws_id:
            qs = qs.filter(extraction__workspace_id=ws_id)

        return qs

    def perform_create(self, serializer):
        extraction = serializer.validated_data.get('extraction')
        if extraction:
            user = self.request.user
            if not getattr(user, 'is_superuser', False):
                has_access = WorkspaceMember.objects.filter(
                    workspace=extraction.workspace, user=user
                ).exists()
                if not has_access:
                    raise PermissionDenied("You do not have access to this workspace.")
        serializer.save(verified_by=self.request.user)

    def perform_update(self, serializer):
        hitl = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=hitl.extraction.workspace, user=user
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have access to this workspace.")
        serializer.save(verified_by=self.request.user)

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.extraction.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to delete HITL corrections in this workspace.")
        instance.delete()
