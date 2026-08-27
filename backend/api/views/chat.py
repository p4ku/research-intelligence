from rest_framework import viewsets, status, permissions, serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from research_intelligence.models import WorkspaceMember


class ChatRequestSerializer(serializers.Serializer):
    question = serializers.CharField(required=True, help_text="Research question or prompt")
    workspace_id = serializers.UUIDField(required=True, help_text="Workspace UUID containing literature corpus")


class ChatResponseSerializer(serializers.Serializer):
    answer = serializers.CharField(help_text="Synthesized response grounded in literature")
    citations = serializers.ListField(child=serializers.CharField(), help_text="Referenced papers and evidence quotes")


class ChatViewSet(viewsets.ViewSet):
    """
    RAG interactive query sessions over ingested research papers.
    Validates workspace access before processing queries.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChatRequestSerializer,
        responses={
            200: ChatResponseSerializer,
            400: OpenApiResponse(description="Invalid request - Missing question or workspace_id"),
            403: OpenApiResponse(description="Forbidden - User is not a member of this workspace"),
        },
        tags=['Chat & Knowledge Explorer']
    )
    def create(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data["question"]
        workspace_id = serializer.validated_data["workspace_id"]

        # Verify workspace access
        user = request.user
        if not getattr(user, 'is_superuser', False):
            if not WorkspaceMember.objects.filter(workspace_id=workspace_id, user=user).exists():
                return Response(
                    {"error": "Access denied. You are not a member of this workspace."},
                    status=status.HTTP_403_FORBIDDEN
                )

        return Response({
            "answer": f"Mocked RAG response for: '{question}' in workspace {workspace_id}",
            "citations": []
        }, status=status.HTTP_200_OK)
