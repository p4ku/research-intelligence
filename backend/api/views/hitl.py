from rest_framework import viewsets, serializers, permissions
from research_intelligence.models import HITLCorrection, WorkspaceMember


class HITLCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HITLCorrection
        fields = '__all__'


class HITLViewSet(viewsets.ModelViewSet):
    """
    Scientists validation overrides (verify, modify, reject).
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = HITLCorrectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return HITLCorrection.objects.all()
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return HITLCorrection.objects.filter(extraction__workspace_id__in=user_ws_ids)
