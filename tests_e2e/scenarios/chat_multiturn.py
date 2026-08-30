"""
Multi-Turn Conversational Q&A & Gemini Context Caching Scenario.
"""

import logging
from typing import Dict, Any, Optional
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    PipelineService,
    ChatService,
)

logger = logging.getLogger("e2e_chat_multiturn")


def run_chat_multiturn_scenario(
    workspace_id: str,
    paper_id: str,
    config: Optional[E2EConfig] = None
) -> Dict[str, Any]:
    """
    Executes a 2-turn deep scientific dialogue with an ingested paper:
    Turn 1: Core algorithmic & benchmark query (provisions session & Gemini cache).
    Turn 2: Contextual follow-up query referencing Turn 1 with session_id.
    """
    cfg = config or E2EConfig.from_env()
    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    chat_svc = ChatService(client)

    logger.info("=================================================================")
    logger.info("💬 STARTING MULTI-TURN PAPER CHAT & CONTEXT CACHING SCENARIO")
    logger.info(f"📍 Workspace ID : {workspace_id}")
    logger.info(f"📄 Paper ID     : {paper_id}")
    logger.info("=================================================================")

    # Turn 1: Core algorithmic query
    q1 = "What core machine learning architecture, optimization benchmark, or methodology is evaluated in this paper?"
    logger.info(f"🗣️ [Turn 1 Question]: '{q1}'")
    turn1_resp = chat_svc.ask_paper_sync(
        workspace_id=workspace_id,
        paper_id=paper_id,
        question=q1,
        deep_thinking=True,
    )
    session_id = str(turn1_resp.get("session") or turn1_resp.get("session_id") or "")
    ans1 = turn1_resp.get("message") or turn1_resp.get("answer") or ""
    citations1 = turn1_resp.get("citations") or turn1_resp.get("visual_citations") or []
    tokens1 = turn1_resp.get("total_tokens") or (turn1_resp.get("tokens_in", 0) + turn1_resp.get("tokens_out", 0))

    assert session_id, "Turn 1 failed to return a valid session_id"
    assert len(ans1) > 20, f"Turn 1 returned empty answer: {ans1}"
    logger.info(f"🤖 [Turn 1 Answer]: {ans1[:160]}...")
    logger.info(f"   • Session ID : {session_id}")
    logger.info(f"   • Citations  : {len(citations1)} grounded")
    logger.info(f"   • Tokens     : {tokens1:,}")

    # Turn 2: Follow-up question relying on multi-turn context
    q2 = "Based on the approach you just described, what are the primary limitations, computational trade-offs, or open challenges acknowledged by the authors?"
    logger.info(f"🗣️ [Turn 2 Follow-Up Question]: '{q2}'")
    turn2_resp = chat_svc.ask_paper_sync(
        workspace_id=workspace_id,
        paper_id=paper_id,
        question=q2,
        session_id=session_id,
        deep_thinking=True,
    )
    ans2 = turn2_resp.get("message") or turn2_resp.get("answer") or ""
    citations2 = turn2_resp.get("citations") or turn2_resp.get("visual_citations") or []
    tokens2 = turn2_resp.get("total_tokens") or (turn2_resp.get("tokens_in", 0) + turn2_resp.get("tokens_out", 0))

    assert len(ans2) > 20, f"Turn 2 returned empty answer: {ans2}"
    logger.info(f"🤖 [Turn 2 Answer]: {ans2[:160]}...")
    logger.info(f"   • Citations  : {len(citations2)} grounded")
    logger.info(f"   • Tokens     : {tokens2:,}")

    total_tokens = tokens1 + tokens2
    total_cost = float(turn1_resp.get("usd_cost", 0.0)) + float(turn2_resp.get("usd_cost", 0.0))

    logger.info("=================================================================")
    logger.info(f"🎉 MULTI-TURN CHAT SCENARIO COMPLETED (2 Turns • {total_tokens:,} tokens • ${total_cost:.4f} USD)")
    logger.info("=================================================================")

    return {
        "status": "completed",
        "session_id": session_id,
        "turn1": {
            "question": q1,
            "answer_snippet": ans1[:180] + "...",
            "citations_count": len(citations1),
            "tokens": tokens1,
        },
        "turn2": {
            "question": q2,
            "answer_snippet": ans2[:180] + "...",
            "citations_count": len(citations2),
            "tokens": tokens2,
        },
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
    }
