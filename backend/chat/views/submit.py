import logging
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from chat.models import PaperChatSession, PaperChatMessage
from research_intelligence.models import Paper, Workspace, PipelineRun
from chat.serializers import (
    PaperChatMessageSerializer,
    PaperChatSubmitSerializer,
    PaperChatAsyncResponseSerializer,
)
from chat.tasks import execute_paper_chat_task
from chat.engine import PaperChatEngine
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatSubmitView(APIView):
    """
    Main entrypoint for submitting interactive Q&A research questions about a specific paper or workspace.
    Dispatches to Celery background task by default (returning 202 Accepted) or executes synchronously with ?sync=true.
    """
    permission_classes = [permissions.IsAuthenticated]

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
        paper_id = data.get('paper_id')
        workspace_id = data.get('workspace_id')
        session_id = data.get('session_id')
        question = data['question'].strip()
        is_sync = data.get('sync', False)
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
                paper = None
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

        # If explicit workspace_id was passed with a paper, ensure it matches paper's workspace
        if workspace_id and paper and str(paper.workspace_id) != str(workspace_id):
            return Response(
                {"error": "Mismatch between provided workspace_id and paper's workspace."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. RBAC Access Control Check
        workspace, membership, error_msg = check_workspace_access(
            request.user,
            str(target_workspace.id),
            required_roles=['admin', 'manager', 'researcher']
        )
        if error_msg:
            return Response({"error": error_msg}, status=status.HTTP_403_FORBIDDEN)

        # 3. Resolve or Create Chat Session
        session = None
        if session_id:
            try:
                session = PaperChatSession.objects.get(id=session_id, workspace=target_workspace)
            except PaperChatSession.DoesNotExist:
                return Response(
                    {"error": f"Chat session '{session_id}' not found in workspace."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if session.user_id and session.user_id != request.user.id:
                if not (request.user.is_staff or request.user.is_superuser):
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

        # 4. Create Pending Message Record
        message = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            status='pending',
            question=question,
            deep_thinking=deep_thinking
        )

        # Synchronous execution flow
        if is_sync:
            result = PaperChatEngine().execute(message)
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
        # In test environments or when caller expects 200 on async or 202
        return Response(
            PaperChatAsyncResponseSerializer(async_response_data).data,
            status=status.HTTP_202_ACCEPTED
        )
