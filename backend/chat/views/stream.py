import logging
from django.http import StreamingHttpResponse
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from chat.models import PaperChatMessage
from chat.serializers import PaperChatSubmitSerializer
from chat.engine import PaperChatEngine
from api.throttles import ChatRateThrottle
from .scope import resolve_chat_target

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
        target, error = resolve_chat_target(request, data)
        if error:
            return error

        message = PaperChatMessage.objects.create(
            session=target.session,
            sender='user',
            status='pending',
            question=data['question'].strip(),
            deep_thinking=data.get('deep_thinking', False)
        )

        response = StreamingHttpResponse(
            PaperChatEngine().execute_stream(message),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
