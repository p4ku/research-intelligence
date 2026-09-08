import logging
from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from chat.models import PaperChatSession, PaperChatMessage
from research_intelligence.models import Paper, Workspace
from chat.serializers import PaperChatSubmitSerializer
from chat.engine import PaperChatEngine
from research_intelligence.services import check_workspace_access
from api.throttles import ChatRateThrottle

logger = logging.getLogger(__name__)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatStreamView(APIView):
    """
    Server-Sent Events (SSE) streaming endpoint for interactive research Q&A.
    Yields live tokens, citations, fact-checking audit, and usage metrics via text/event-stream.
    Throttled at 20 requests/minute per user to guard against LLM token depletion.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    @extend_schema(
        request=PaperChatSubmitSerializer,
        responses={
            200: OpenApiResponse(description="Live SSE stream (text/event-stream)"),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Paper or Workspace not found")
        }
    )
    def post(self, request):
        serializer = PaperChatSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        paper_id = data.get('paper_id')
        workspace_id = data.get('workspace_id')
        session_id = data.get('session_id')
        question = data['question'].strip()
        deep_thinking = data.get('deep_thinking', False)

        paper = None
        target_workspace = None

        if paper_id:
            try:
                paper = Paper.objects.select_related('workspace').get(id=paper_id)
                target_workspace = paper.workspace
            except Paper.DoesNotExist:
                return Response(
                    {"error": f"Paper with id '{paper_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif workspace_id:
            try:
                target_workspace = Workspace.objects.get(id=workspace_id)
            except Workspace.DoesNotExist:
                return Response(
                    {"error": f"Workspace with id '{workspace_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {"error": "Either paper_id or workspace_id must be provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # RBAC Check
        workspace, membership, error_msg = check_workspace_access(
            request.user,
            str(target_workspace.id),
            required_roles=['admin', 'manager', 'researcher']
        )
        if error_msg:
            return Response({"error": error_msg}, status=status.HTTP_403_FORBIDDEN)

        # Resolve or create Session
        session = None
        if session_id:
            try:
                session = PaperChatSession.objects.get(id=session_id, workspace=target_workspace)
            except (PaperChatSession.DoesNotExist, ValueError, ValidationError):
                return Response(
                    {"error": f"Chat session '{session_id}' not found in workspace."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if session.user_id and session.user_id != request.user.id:
                is_admin = WorkspaceMember.objects.filter(
                    workspace=target_workspace, user=request.user, role__in=['admin', 'manager']
                ).exists()
                if not is_admin:
                    return Response(
                        {"error": "You do not have permission to append to another user's chat session."},
                        status=status.HTTP_403_FORBIDDEN
                    )
        else:
            session = PaperChatSession.objects.create(
                workspace=target_workspace,
                paper=paper,
                user=request.user,
                title=(question[:50] + "...") if len(question) > 50 else question
            )

        # Create Message
        message = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            status='pending',
            question=question,
            deep_thinking=deep_thinking
        )

        response = StreamingHttpResponse(
            PaperChatEngine().execute_stream(message),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
