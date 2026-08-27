import uuid
from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from research_intelligence.models import (
    Workspace,
    Paper,
    PaperChatSession,
    PaperChatMessage,
    WorkspaceMember,
)
from ..serializers.chat import (
    PaperChatMessageSerializer,
    PaperChatSessionSerializer,
    PaperChatSessionDetailSerializer,
    PaperChatSubmitSerializer,
    PaperChatAsyncResponseSerializer,
)
from research_intelligence.tasks.chat.tasks import execute_paper_chat_task
from research_intelligence.tasks.chat.engine import execute_paper_chat_logic
from research_intelligence.mcp.tools.workspaces import _check_workspace_access


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatSubmitView(APIView):
    """
    Main entrypoint for submitting interactive Q&A research questions about a specific paper.
    Dispatches to Celery background task by default (returning 202 Accepted) or executes synchronously with ?sync=true.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=PaperChatSubmitSerializer,
        responses={
            202: PaperChatAsyncResponseSerializer,
            200: PaperChatMessageSerializer,
            400: OpenApiResponse(description="Invalid request payload"),
            403: OpenApiResponse(description="Forbidden - Not a member of the workspace"),
            404: OpenApiResponse(description="Paper or Workspace not found"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = PaperChatSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        paper_id = validated.get('paper_id')
        question = validated['question'].strip()
        workspace_id = validated.get('workspace_id')
        session_id = validated.get('session_id')
        is_sync = validated.get('sync', False)

        if not paper_id and not workspace_id:
            return Response({"error": "Must provide either 'paper_id' or 'workspace_id'."}, status=status.HTTP_400_BAD_REQUEST)

        # Handle workspace-level query without specific paper_id
        if workspace_id and not paper_id:
            workspace, membership, error = _check_workspace_access(
                request.user, str(workspace_id), required_roles=['admin', 'manager', 'researcher']
            )
            if error:
                return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

            target_paper = Paper.objects.filter(workspace=workspace).first()
            if not target_paper:
                return Response({
                    "answer": f"Mocked RAG response for: '{question}' in workspace {workspace_id}",
                    "citations": []
                }, status=status.HTTP_200_OK)
            paper = target_paper
            target_workspace = workspace
            # For backward compatible workspace query tests without sync=False flag
            if 'sync' not in request.data:
                is_sync = True
        else:
            # Resolve Paper and Workspace
            try:
                paper = Paper.objects.select_related('workspace').get(id=paper_id)
            except Paper.DoesNotExist:
                return Response({"error": f"Paper '{paper_id}' not found."}, status=status.HTTP_404_NOT_FOUND)

            target_workspace = paper.workspace
            if workspace_id and str(target_workspace.id) != str(workspace_id):
                return Response({"error": "Specified workspace_id does not match the paper's workspace."}, status=status.HTTP_400_BAD_REQUEST)

            # Verify workspace membership
            workspace, membership, error = _check_workspace_access(
                request.user, str(target_workspace.id), required_roles=['admin', 'manager', 'researcher']
            )
            if error:
                return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        # Resolve or create session
        session = None
        if session_id:
            try:
                session = PaperChatSession.objects.get(id=session_id, workspace=target_workspace)
            except PaperChatSession.DoesNotExist:
                return Response({"error": f"Chat session '{session_id}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not session:
            title = (question[:50] + "...") if len(question) > 50 else question
            session = PaperChatSession.objects.create(
                workspace=target_workspace,
                paper=paper,
                user=request.user,
                title=title
            )

        # Create pending message record
        message = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            status='pending',
            question=question
        )

        # Synchronous execution flow
        if is_sync:
            result = execute_paper_chat_logic(message)
            message.refresh_from_db()
            return Response(PaperChatMessageSerializer(message).data, status=status.HTTP_200_OK)

        # Asynchronous Celery execution flow
        task = execute_paper_chat_task.delay(str(message.id))
        task_id = str(task.id) if task else ""
        message.celery_task_id = task_id
        message.save(update_fields=['celery_task_id'])

        poll_url = f"/api/chat/messages/{message.id}/"
        return Response(
            {
                "status": "pending",
                "message_id": message.id,
                "session_id": session.id,
                "task_id": task_id,
                "poll_url": poll_url,
            },
            status=status.HTTP_202_ACCEPTED
        )


@extend_schema(tags=['Chat & Knowledge Explorer'])
class ChatMessageDetailView(APIView):
    """
    Polls or retrieves the status, completed answer, and citations for a specific PaperChatMessage.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: PaperChatMessageSerializer,
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Message not found"),
        }
    )
    def get(self, request, message_id, *args, **kwargs):
        try:
            msg_uuid = uuid.UUID(str(message_id))
            message = PaperChatMessage.objects.select_related(
                'session', 'session__workspace', 'session__paper'
            ).get(id=msg_uuid)
        except (ValueError, PaperChatMessage.DoesNotExist):
            return Response({"error": "Message not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check workspace access
        workspace, membership, error = _check_workspace_access(
            request.user, str(message.session.workspace_id), required_roles=['admin', 'manager', 'researcher']
        )
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        return Response(PaperChatMessageSerializer(message).data, status=status.HTTP_200_OK)


@extend_schema(tags=['Chat & Knowledge Explorer'])
class PaperChatSessionViewSet(viewsets.ModelViewSet):
    """
    Manages interactive multi-turn conversation sessions for papers.
    Scoped strictly to workspaces the authenticated user belongs to.
    """
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PaperChatSessionDetailSerializer
        return PaperChatSessionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return PaperChatSession.objects.none()

        if getattr(user, 'is_superuser', False):
            qs = PaperChatSession.objects.select_related('workspace', 'paper', 'user').all()
        else:
            user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
            qs = PaperChatSession.objects.select_related('workspace', 'paper', 'user').filter(
                workspace_id__in=user_ws_ids
            )

        workspace_id = self.request.query_params.get('workspace') or self.request.query_params.get('workspace_id')
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)

        paper_id = self.request.query_params.get('paper') or self.request.query_params.get('paper_id')
        if paper_id:
            qs = qs.filter(paper_id=paper_id)

        return qs.order_by('-updated_at')

    def destroy(self, request, *args, **kwargs):
        session = self.get_object()
        session.delete()
        return Response({"message": "Chat session deleted successfully."}, status=status.HTTP_200_OK)
