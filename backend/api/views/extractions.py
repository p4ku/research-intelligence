from rest_framework import viewsets, serializers, permissions
from research_intelligence.models import Extraction, WorkspaceMember


class ExtractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Extraction
        fields = '__all__'


class ExtractionViewSet(viewsets.ModelViewSet):
    """
    Lists extracted claims and parameters matching schema settings.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = ExtractionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return Extraction.objects.all()
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return Extraction.objects.filter(workspace_id__in=user_ws_ids)
