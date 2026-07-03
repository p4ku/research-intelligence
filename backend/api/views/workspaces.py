from rest_framework import viewsets
from research_intelligence.models import Workspace
from ..serializers.workspaces import WorkspaceSerializer

class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace (Projects) and prompt limits configurations.
    """
    queryset = Workspace.objects.all()
    serializer_class = WorkspaceSerializer
