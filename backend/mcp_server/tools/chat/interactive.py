import json
import uuid
import logging
from typing import Optional, Dict, Any
from research_intelligence.models import Workspace, Paper
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)


def ask_paper_logic(
    user,
    workspace_id: str,
    question: str,
    paper_id: str | None = None,
    session_id: str | None = None,
    deep_thinking: bool = False
) -> str:
    """
    Interrogates an ingested academic paper or whole workspace using the workspace's configured LLM (e.g. Gemini 3.8 Flash).
    Injects full text (OCR Markdown or raw multimodal PDF), screening evaluations, dynamic extractions,
    and mathematical signal scoring metrics.
    Maintains multi-turn conversation session history if session_id is provided.
    """
    if not workspace_id or not question:
        return json.dumps({"status": "error", "error": "Must provide 'workspace_id' and 'question'."}, indent=2)

    workspace, membership, error = check_workspace_access(
        user, workspace_id, required_roles=['admin', 'manager', 'researcher']
    )
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    paper = None
    if paper_id:
        try:
            p_uuid = uuid.UUID(paper_id)
            paper = Paper.objects.select_related('workspace').get(id=p_uuid, workspace=workspace)
        except (ValueError, Paper.DoesNotExist):
            return json.dumps({"status": "error", "error": f"Paper '{paper_id}' not found in workspace '{workspace.name}'."}, indent=2)

    from chat.models import PaperChatSession, PaperChatMessage
    from chat.engine import PaperChatEngine

    session = None
    if session_id:
        try:
            s_uuid = uuid.UUID(session_id)
            session = PaperChatSession.objects.get(id=s_uuid, workspace=workspace)
        except (ValueError, PaperChatSession.DoesNotExist):
            return json.dumps({"status": "error", "error": f"Chat session '{session_id}' not found in workspace '{workspace.name}'."}, indent=2)

    if not session:
        session = PaperChatSession.objects.create(
            workspace=workspace,
            paper=paper,
            user=user if getattr(user, 'is_authenticated', False) or getattr(user, 'id', None) else None,
            title=(question[:50] + "...") if len(question) > 50 else question
        )

    # Create message entry
    message = PaperChatMessage.objects.create(
        session=session,
        sender='user',
        status='pending',
        question=question.strip(),
        deep_thinking=deep_thinking
    )

    # Execute synchronous generation for FastMCP client
    try:
        res = PaperChatEngine().execute(message)
        return json.dumps(res, indent=2)
    except Exception as e:
        logger.exception(f"Error executing chat for paper: {e}")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


__all__ = [
    "ask_paper_logic",
]
