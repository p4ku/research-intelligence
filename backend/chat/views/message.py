import logging
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from chat.models import PaperChatMessage
from chat.serializers import PaperChatMessageSerializer
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatMessageDetailView(APIView):
    """
    Polling and retrieval endpoint for an individual chat message turn.
    Returns generated answer, citations, status, tokens, cost, and timestamps.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: PaperChatMessageSerializer,
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Message not found")
        }
    )
    def get(self, request, message_id):
        try:
            message = PaperChatMessage.objects.select_related(
                'session',
                'session__workspace',
                'session__paper'
            ).get(id=message_id)
        except (ValueError, PaperChatMessage.DoesNotExist):
            return Response(
                {"error": f"Chat message '{message_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # RBAC Check
        workspace, membership, error_msg = check_workspace_access(
            request.user,
            str(message.session.workspace_id),
            required_roles=['admin', 'manager', 'researcher']
        )
        if error_msg:
            return Response({"error": error_msg}, status=status.HTTP_403_FORBIDDEN)

        return Response(PaperChatMessageSerializer(message).data, status=status.HTTP_200_OK)
