import logging
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from chat.models import PaperChatMessage
from chat.serializers import (
    PaperChatMessageSerializer,
    PaperChatSubmitSerializer,
    PaperChatAsyncResponseSerializer,
)
from chat.tasks import execute_paper_chat_task
from chat.engine import PaperChatEngine
from api.throttles import ChatRateThrottle
from .scope import resolve_chat_target

logger = logging.getLogger(__name__)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatSubmitView(APIView):
    """
    Main entrypoint for submitting interactive Q&A research questions about a specific paper or workspace.
    Dispatches to Celery background task by default (returning 202 Accepted) or executes synchronously with ?sync=true.
    Throttled at 20 requests/minute per user to guard against LLM token depletion.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    @extend_schema(
        request=PaperChatSubmitSerializer,
        responses={
            202: PaperChatAsyncResponseSerializer,
            200: PaperChatMessageSerializer,
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
        is_sync = data.get('sync', False)

        target, error = resolve_chat_target(request, data)
        if error:
            return error
        paper, session = target.paper, target.session

        message = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            status='pending',
            question=data['question'].strip(),
            deep_thinking=data.get('deep_thinking', False)
        )

        # Synchronous execution flow
        if is_sync:
            PaperChatEngine().execute(message)
            message.refresh_from_db()
            return Response(PaperChatMessageSerializer(message).data, status=status.HTTP_200_OK)

        # Asynchronous Celery execution flow
        task = execute_paper_chat_task.delay(str(message.id))
        task_id = str(task.id) if task else ""
        message.celery_task_id = task_id
        message.save(update_fields=['celery_task_id'])

        async_response_data = {
            "status": "pending",
            "message_id": message.id,
            "session_id": session.id,
            "task_id": task_id,
            "paper_id": paper.id if paper else None,
            "question": message.question,
            "deep_thinking": message.deep_thinking,
            "created_at": message.created_at
        }
        return Response(
            PaperChatAsyncResponseSerializer(async_response_data).data,
            status=status.HTTP_202_ACCEPTED
        )
