from rest_framework import viewsets, serializers, permissions
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from research_intelligence.models import HITLCorrection, WorkspaceMember


class HITLCorrectionSerializer(serializers.ModelSerializer):
    human_operator = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = HITLCorrection
        fields = '__all__'
        read_only_fields = ['id', 'timestamp']


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
        base_qs = HITLCorrection.objects.select_related('extraction', 'extraction__workspace')
        if getattr(user, 'is_superuser', False):
            qs = base_qs.all().order_by('-timestamp')
        else:
            user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
            if not user_ws_ids:
                return HITLCorrection.objects.none()
            qs = base_qs.filter(extraction__workspace_id__in=user_ws_ids).order_by('-timestamp')

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
        operator = serializer.validated_data.get('human_operator')
        if not operator:
            operator = getattr(self.request.user, 'email', '') or getattr(self.request.user, 'username', '') or 'system'
        instance = serializer.save(human_operator=operator)
        if extraction:
            extraction.is_hitl_validated = True
            update_fields = ['is_hitl_validated']
            if instance.action == 'modify' and instance.corrected_value is not None:
                if isinstance(instance.corrected_value, dict) and isinstance(extraction.fields_data, dict):
                    extraction.fields_data.update(instance.corrected_value)
                else:
                    extraction.fields_data = instance.corrected_value
                update_fields.append('fields_data')
            extraction.save(update_fields=update_fields)

    def perform_update(self, serializer):
        hitl = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=hitl.extraction.workspace, user=user
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have access to this workspace.")
        operator = serializer.validated_data.get('human_operator')
        if not operator:
            operator = getattr(self.request.user, 'email', '') or getattr(self.request.user, 'username', '') or 'system'
        serializer.save(human_operator=operator)

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.extraction.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to delete HITL corrections in this workspace.")
        instance.delete()
