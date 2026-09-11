"""
Resolves what a chat request is about — the paper or workspace, the caller's
membership, and the session the turn joins or starts. Shared by the sync
submit view and the SSE stream view so the two cannot drift apart again.
"""
import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response

from chat.models import PaperChatSession
from research_intelligence.models import Paper, Workspace
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)

CHAT_ROLES = ['admin', 'manager', 'researcher']
OVERSEER_ROLES = ('admin', 'manager')


@dataclass
class ChatTarget:
    paper: Paper | None
    workspace: Workspace
    session: PaperChatSession


def _error(message: str, http_status: int) -> Response:
    return Response({"error": message}, status=http_status)


def resolve_chat_target(request, data: dict) -> tuple[ChatTarget | None, Response | None]:
    """
    Turns validated submit data into the (paper, workspace, session) a turn
    targets, or an error response.

    Rules:
    - exactly one of paper_id / workspace_id names the scope; a workspace_id
      given alongside a paper must be the paper's own;
    - the caller must hold a chat-capable role in that workspace;
    - a session_id must belong to that workspace AND to the same paper (or to
      no paper, for workspace-scope chat) — a thread never changes subject;
    - only the session's owner, or a workspace admin/manager, may append to it.
    """
    paper_id = data.get('paper_id')
    workspace_id = data.get('workspace_id')
    session_id = data.get('session_id')
    question = data['question'].strip()

    paper = None
    if paper_id:
        try:
            paper = Paper.objects.select_related('workspace').get(id=paper_id)
        except Paper.DoesNotExist:
            return None, _error(f"Paper with id '{paper_id}' not found.", status.HTTP_404_NOT_FOUND)
        target_workspace = paper.workspace
        if workspace_id and str(paper.workspace_id) != str(workspace_id):
            return None, _error(
                "Mismatch between provided workspace_id and paper's workspace.",
                status.HTTP_400_BAD_REQUEST,
            )
    elif workspace_id:
        try:
            target_workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return None, _error(f"Workspace with id '{workspace_id}' not found.", status.HTTP_404_NOT_FOUND)
    else:
        return None, _error("Either paper_id or workspace_id must be provided.", status.HTTP_400_BAD_REQUEST)

    workspace, membership, error_msg = check_workspace_access(
        request.user, str(target_workspace.id), required_roles=CHAT_ROLES
    )
    if error_msg:
        return None, _error(error_msg, status.HTTP_403_FORBIDDEN)

    if session_id:
        try:
            session = PaperChatSession.objects.get(id=session_id, workspace=target_workspace)
        except (PaperChatSession.DoesNotExist, ValueError, ValidationError):
            return None, _error(
                f"Chat session '{session_id}' not found in workspace.", status.HTTP_404_NOT_FOUND
            )
        # An ownerless session (MCP creates them for an unauthenticated caller)
        # is nobody's to continue: the list route hides it from everyone but
        # admins and managers, so the write path says the same (PR #174).
        if session.user_id != request.user.id:
            if getattr(membership, 'role', None) not in OVERSEER_ROLES:
                return None, _error(
                    "You do not have permission to append to another user's chat session.",
                    status.HTTP_403_FORBIDDEN,
                )
        if session.paper_id != (paper.id if paper else None):
            return None, _error(
                "Chat session belongs to a different paper.", status.HTTP_400_BAD_REQUEST
            )
    else:
        session = PaperChatSession.objects.create(
            workspace=target_workspace,
            paper=paper,
            user=request.user,
            title=(question[:50] + "...") if len(question) > 50 else question,
        )

    return ChatTarget(paper=paper, workspace=target_workspace, session=session), None
