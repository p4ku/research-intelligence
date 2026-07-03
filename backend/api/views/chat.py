from rest_framework import viewsets, status
from rest_framework.response import Response

class ChatViewSet(viewsets.ViewSet):
    """
    RAG interactive query sessions over ingested research papers.
    """
    def create(self, request):
        question = request.data.get("question")
        workspace_id = request.data.get("workspace_id")
        # Mock RAG response
        return Response({
            "answer": f"Mocked RAG response for: '{question}' in workspace {workspace_id}",
            "citations": []
        }, status=status.HTTP_200_OK)
