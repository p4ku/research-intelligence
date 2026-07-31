from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from research_intelligence.models import WorkspaceMember


class ChatViewSet(viewsets.ViewSet):
    """
    RAG interactive query sessions over ingested research papers.
    Validates workspace access before processing queries.
    """
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request):
        question = request.data.get("question")
        workspace_id = request.data.get("workspace_id")

        if not workspace_id:
            return Response(
                {"error": "Must provide 'workspace_id'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify workspace access
        user = request.user
        if not getattr(user, 'is_superuser', False):
            if not WorkspaceMember.objects.filter(workspace_id=workspace_id, user=user).exists():
                return Response(
                    {"error": "Access denied. You are not a member of this workspace."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Mock RAG response
        return Response({
            "answer": f"Mocked RAG response for: '{question}' in workspace {workspace_id}",
            "citations": []
        }, status=status.HTTP_200_OK)
