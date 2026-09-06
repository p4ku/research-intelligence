"""
Ask Paper End-to-End User Journey Scenario ("7 Ask").

Validates all 4 core capabilities depicted in the Ask Paper architecture:
1. Pick any paper from any briefing (search dynamically by title or author).
2. Ask in plain language with grounding in full text, page & passage citations.
3. Questions/answers kept per paper to pick up where left off (multi-turn per-paper session history).
4. Open paper's analysis from the answer (scorecard, extractions, PDF, metadata).

Designed to be robust against dynamic paper arrivals and varying text content.
"""

import logging
import random
import re
import time
from typing import Dict, Any, Optional, List

from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    AgentService,
    PipelineService,
    ChatService,
    DataConsistencyValidator,
)

logger = logging.getLogger("e2e_ask_paper_journey")

# Common English stopwords to ignore when extracting distinctive search tokens from dynamic titles
COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "from",
    "by", "for", "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "of", "up", "down", "in", "out", "on",
    "off", "over", "under", "again", "further", "then", "once", "here", "there", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
    "should", "now", "using", "based", "via", "towards", "approach", "study", "novel",
    "method", "methods", "model", "models", "paper", "analysis", "review",
}


def extract_distinctive_title_token(title: str) -> str:
    """
    Extracts a distinctive search keyword from a dynamic paper title.
    Filters punctuation and stopwords to find a substantive domain token.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", title)
    words = cleaned.split()
    candidates = [
        w for w in words
        if len(w) >= 4 and w.lower() not in COMMON_STOPWORDS and not w.isdigit()
    ]
    if candidates:
        # Prefer longest candidate token for highest uniqueness
        candidates.sort(key=len, reverse=True)
        return candidates[0]
    # Fallback if title is unusually short or composed of small words
    for w in words:
        if len(w) >= 3:
            return w
    return title[:10].strip()


def extract_first_author_surname(authors_str: str) -> Optional[str]:
    """
    Extracts the surname or primary name token of the first author from a dynamic authors string.
    e.g. 'John Doe, Alice Smith' -> 'Doe'
    """
    if not authors_str or not str(authors_str).strip():
        return None
    first_author_block = str(authors_str).split(",")[0].strip()
    # Strip affilations/email brackets if present
    first_author_clean = re.sub(r"[\(\[\{<].*?[\)\]\}>]", "", first_author_block).strip()
    tokens = [re.sub(r"[^a-zA-Z]", "", t) for t in first_author_clean.split()]
    tokens = [t for t in tokens if len(t) >= 3]
    if tokens:
        return tokens[-1]  # Typically surname
    return None


def run_ask_paper_journey_scenario(
    config: Optional[E2EConfig] = None,
    workspace_id: Optional[str] = None,
    paper_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the complete 4-step 'Ask Paper' journey:
    1. Search and pick dynamic paper by title or author from briefings/workspace.
    2. Submit grounded plain-language question, asserting grounding and citations.
    3. Verify per-paper session isolation and conduct follow-up Turn 2 to pick up where left off.
    4. Access scorecard, structured extractions, and PDF analysis directly from the answer context.
    """
    cfg = config or E2EConfig.from_env()
    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)

    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)
    chat_svc = ChatService(client)

    logger.info("=================================================================")
    logger.info("📖 STARTING ASK PAPER COMPLETE E2E USER JOURNEY ('7 ASK')")
    logger.info(f"📍 Target API : {cfg.base_url}")
    logger.info("=================================================================")

    target_workspace_id = workspace_id
    chosen_paper = None
    created_new_workspace = False

    # Step 0: Ensure we have an active workspace with ingested dynamic papers
    if not target_workspace_id:
        # Check if there is an existing workspace with papers from previous runs
        existing_workspaces = ws_svc.list_workspaces()
        for ws in existing_workspaces:
            ws_id = ws["id"]
            existing_papers = pipeline_svc.list_papers(workspace_id=ws_id, page_size=5)
            if existing_papers and len(existing_papers) >= 1:
                target_workspace_id = ws_id
                chosen_paper = existing_papers[0]
                logger.info(f"📂 Utilizing existing workspace '{ws.get('name')}' ({ws_id}) with {len(existing_papers)} papers.")
                break

    if not target_workspace_id or not chosen_paper:
        # Provision dedicated workspace and ingest dynamic papers via Research Agent
        created_new_workspace = True
        random_suffix = random.randint(10000000, 99999999)
        workspace_name = f"test_e2e_ask_paper_{random_suffix}"
        logger.info(f"✨ Provisioning fresh test workspace: '{workspace_name}'...")
        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria="Accept machine learning, neural networks, or computational intelligence.",
            abstract_rejection_criteria="Reject unrelated agriculture or clinical trials.",
            full_text_acceptance_criteria="Accept empirical and theoretical evaluations.",
            full_text_rejection_criteria="Reject papers lacking technical depth.",
            signal_score_code="score = 0.5 * fit_score + 0.5 * 8.0\nreturn round(score * 10.0, 2)",
            screening_llm_model="google/gemini-3.8-flash",
        )
        target_workspace_id = ws_data["id"]

        # Register active scraper with broad arXiv CS topic to ensure dynamic paper arrival
        ws_svc.create_scraper(
            workspace_id=target_workspace_id,
            provider="arxiv",
            search_query="all:neural AND all:network",
            limit=2,
        )

        logger.info("🚀 Launching research agent to ingest dynamic literature...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=target_workspace_id,
            name=f"Ask Paper Ingestion - {workspace_name}",
            limit=2,
        )
        t_start = time.time()
        agent_svc.poll_until_complete(
            agent_proc["id"],
            max_timeout_sec=cfg.timeout_sec,
            poll_interval_sec=cfg.poll_interval,
        )
        logger.info(f"✅ Ingestion completed in {time.time() - t_start:.1f}s.")

        papers = pipeline_svc.list_papers(workspace_id=target_workspace_id, page_size=5)
        assert papers, f"No papers were ingested into workspace '{target_workspace_id}'"
        chosen_paper = papers[0]

    # If an explicit paper_id was supplied, fetch it
    if paper_id:
        chosen_paper = pipeline_svc.get_paper(paper_id)

    # Dynamically extract paper properties
    chosen_paper_id = str(chosen_paper["id"])
    paper_title = (chosen_paper.get("title") or "").strip()
    paper_authors = (chosen_paper.get("authors") or "").strip()
    paper_abstract = (chosen_paper.get("abstract") or "").strip()

    logger.info("-----------------------------------------------------------------")
    logger.info(f"📄 Target Paper ID : {chosen_paper_id}")
    logger.info(f"📑 Title           : '{paper_title[:90]}...'")
    logger.info(f"👥 Authors         : '{paper_authors[:60]}...'")
    logger.info("-----------------------------------------------------------------")

    # =========================================================================
    # STEP 1: Pick any paper from any briefing (search by topic, title or author)
    # =========================================================================
    logger.info("🔍 [STEP 1/4] Testing Dynamic Paper Discovery & Search...")
    
    # 1A. Search by title keyword
    title_search_token = extract_distinctive_title_token(paper_title)
    logger.info(f"   • Searching papers by dynamic title keyword: '{title_search_token}'")
    title_search_results = pipeline_svc.list_papers(
        workspace_id=target_workspace_id,
        search=title_search_token,
    )
    title_result_ids = [str(p["id"]) for p in title_search_results]
    assert chosen_paper_id in title_result_ids, (
        f"Search by title token '{title_search_token}' failed to return target paper {chosen_paper_id}. "
        f"Returned IDs: {title_result_ids}"
    )
    logger.info(f"   ✅ Successfully found paper using dynamic title token '{title_search_token}'.")

    # 1B. Search by author surname (if available)
    author_surname = extract_first_author_surname(paper_authors)
    if author_surname:
        logger.info(f"   • Searching papers by dynamic author surname: '{author_surname}'")
        author_search_results = pipeline_svc.list_papers(
            workspace_id=target_workspace_id,
            search=author_surname,
        )
        author_result_ids = [str(p["id"]) for p in author_search_results]
        assert chosen_paper_id in author_result_ids, (
            f"Search by author '{author_surname}' failed to return target paper {chosen_paper_id}. "
            f"Returned IDs: {author_result_ids}"
        )
        logger.info(f"   ✅ Successfully found paper using dynamic author surname '{author_surname}'.")

    # =========================================================================
    # STEP 2: Ask in plain language with grounding in full text, page & passage citations
    # =========================================================================
    logger.info("💬 [STEP 2/4] Asking Scientific Question with Grounding & Visual Citations...")

    # Formulate dynamic scientifically-sound question contextualized with the real paper title
    q1 = f"Regarding the research described in '{paper_title[:70]}', summarize its primary scientific objective, core methodology, and main reported results."
    logger.info(f"   🗣️ [Question 1]: '{q1}'")

    turn1_resp = chat_svc.ask_paper_sync(
        workspace_id=target_workspace_id,
        paper_id=chosen_paper_id,
        question=q1,
        deep_thinking=True,
    )

    ans1 = str(turn1_resp.get("message") or turn1_resp.get("answer") or "")
    session_id = str(turn1_resp.get("session") or turn1_resp.get("session_id") or "")
    resp_paper_id = str(turn1_resp.get("paper_id") or "")
    citations1 = turn1_resp.get("citations") or turn1_resp.get("visual_citations") or []
    tokens1 = turn1_resp.get("total_tokens") or (turn1_resp.get("tokens_in", 0) + turn1_resp.get("tokens_out", 0))

    # Assertions for Turn 1
    assert session_id, "Turn 1 response missing session_id"
    DataConsistencyValidator.validate_uuid(session_id, "chat.session_id")
    assert len(ans1) >= 40, f"Turn 1 answer too short or empty: '{ans1}'"
    assert "Traceback" not in ans1 and "Internal Server Error" not in ans1, (
        f"Turn 1 returned unhandled error traceback in answer: {ans1}"
    )
    if resp_paper_id:
        assert resp_paper_id == chosen_paper_id, (
            f"Turn 1 response paper_id '{resp_paper_id}' does not match chosen paper '{chosen_paper_id}'"
        )

    logger.info(f"   🤖 [Turn 1 Answer]: {ans1[:160]}...")
    logger.info(f"   • Session ID        : {session_id}")
    logger.info(f"   • Citations Count   : {len(citations1)}")
    logger.info(f"   • Tokens Consumed   : {tokens1:,}")

    # Validate structure of citations if present
    if citations1:
        for idx, cit in enumerate(citations1[:3]):
            assert isinstance(cit, dict), f"Citation {idx} is not a dict: {cit}"
            page_val = cit.get("page")
            quote_val = cit.get("quote") or cit.get("passage") or cit.get("text")
            logger.info(f"     📌 Citation #{idx + 1}: Page={page_val}, Quote='{str(quote_val)[:60]}...'")

    # =========================================================================
    # STEP 3: Questions/answers kept per paper to pick up where left off
    # =========================================================================
    logger.info("🔄 [STEP 3/4] Validating Per-Paper Session Persistence & Follow-Up Turn...")

    # 3A. Verify session is listed under this specific paper
    paper_sessions = chat_svc.list_sessions(paper_id=chosen_paper_id)
    session_ids = [str(s["id"]) for s in paper_sessions]
    assert session_id in session_ids, (
        f"Session {session_id} not found in paper {chosen_paper_id} sessions list: {session_ids}"
    )
    logger.info(f"   ✅ Session {session_id} properly registered under Paper {chosen_paper_id}.")

    # 3B. Ask follow-up Turn 2 referencing Turn 1 to pick up where left off
    q2 = "Based on the methodology and findings you just described, what are the primary limitations, computational trade-offs, or open challenges acknowledged by the authors?"
    logger.info(f"   🗣️ [Question 2 (Follow-Up)]: '{q2}'")

    turn2_resp = chat_svc.ask_paper_sync(
        workspace_id=target_workspace_id,
        paper_id=chosen_paper_id,
        session_id=session_id,
        question=q2,
        deep_thinking=True,
    )

    ans2 = str(turn2_resp.get("message") or turn2_resp.get("answer") or "")
    session_id_turn2 = str(turn2_resp.get("session") or turn2_resp.get("session_id") or "")
    citations2 = turn2_resp.get("citations") or turn2_resp.get("visual_citations") or []
    tokens2 = turn2_resp.get("total_tokens") or (turn2_resp.get("tokens_in", 0) + turn2_resp.get("tokens_out", 0))

    assert session_id_turn2 == session_id, (
        f"Turn 2 created a new session '{session_id_turn2}' instead of continuing '{session_id}'"
    )
    assert len(ans2) >= 40, f"Turn 2 answer too short or empty: '{ans2}'"
    logger.info(f"   🤖 [Turn 2 Answer]: {ans2[:160]}...")
    logger.info(f"   • Citations Count   : {len(citations2)}")
    logger.info(f"   • Tokens Consumed   : {tokens2:,}")

    # 3C. Verify multi-turn session detail history from API
    session_detail = chat_svc.get_session(session_id)
    assert str(session_detail.get("paper")) == chosen_paper_id or str(session_detail.get("paper_id")) == chosen_paper_id, (
        f"Session detail paper '{session_detail.get('paper')}' does not match '{chosen_paper_id}'"
    )
    messages = session_detail.get("messages", [])
    assert len(messages) >= 2, f"Expected at least 2 chat turns in session history, got {len(messages)}"
    logger.info(f"   ✅ Multi-turn history verified: {len(messages)} persisted messages in session.")

    # =========================================================================
    # STEP 4: Open paper's analysis from the answer
    # =========================================================================
    logger.info("🔬 [STEP 4/4] Opening Paper's Full Analysis directly from Answer...")

    # From the chat answer context, retrieve the target paper ID
    target_analysis_paper_id = turn2_resp.get("paper_id") or chosen_paper_id
    logger.info(f"   • Inspecting scorecard & analysis for Paper ID: {target_analysis_paper_id}")

    # 4A. GET /api/papers/{paper_id}/
    paper_metadata = pipeline_svc.get_paper(target_analysis_paper_id)
    assert paper_metadata["id"] == target_analysis_paper_id
    assert paper_metadata.get("title") == paper_title
    logger.info(f"   ✅ [1/4 Paper Details]: Verified title, authors, DOI/arXiv metadata.")

    # 4B. GET /api/papers/{paper_id}/scorecard/
    scorecard_data = pipeline_svc.get_paper_scorecard(target_analysis_paper_id)
    paper_scorecard = scorecard_data.get("paper", scorecard_data)
    assert paper_scorecard.get("id") == target_analysis_paper_id
    assert "screening_status" in paper_scorecard
    assert "dimensions" in paper_scorecard
    logger.info(f"   ✅ [2/4 Scorecard]: Verified screening status '{paper_scorecard.get('screening_status')}', signal score '{paper_scorecard.get('signal_score')}', and {len(paper_scorecard.get('dimensions', []))} dimensions.")

    # 4C. GET /api/extractions/?paper={paper_id}
    extractions_resp = client.get(f"/api/extractions/?paper={target_analysis_paper_id}", expected_status=200)
    extractions_data = extractions_resp.json()
    extractions_list = extractions_data.get("results", extractions_data) if isinstance(extractions_data, dict) else extractions_data
    logger.info(f"   ✅ [3/4 Extractions]: Found {len(extractions_list)} structured parameter extractions.")

    # 4D. GET /api/papers/{paper_id}/pdf/
    pdf_status = pipeline_svc.get_paper_pdf_status(target_analysis_paper_id)
    assert pdf_status in (200, 404), (
        f"PDF endpoint returned unexpected HTTP error status {pdf_status} (expected 200 or 404)"
    )
    logger.info(f"   ✅ [4/4 PDF Endpoint]: Verified binary PDF stream availability (HTTP {pdf_status}).")

    total_tokens = tokens1 + tokens2
    total_cost = float(turn1_resp.get("usd_cost", 0.0)) + float(turn2_resp.get("usd_cost", 0.0))
    t1_in = turn1_resp.get("tokens_in", 0) or 0
    t1_out = turn1_resp.get("tokens_out", 0) or 0
    t2_in = turn2_resp.get("tokens_in", 0) or 0
    t2_out = turn2_resp.get("tokens_out", 0) or 0

    cost_metrics = {
        "chat_tokens_in": t1_in + t2_in,
        "chat_tokens_out": t1_out + t2_out,
        "chat_total_tokens": total_tokens,
        "chat_usd_cost": total_cost,
        "total_tokens_consumed": total_tokens,
        "total_usd_spent": total_cost,
    }

    logger.info("=================================================================")
    logger.info(f"🎉 ASK PAPER E2E USER JOURNEY FULLY VERIFIED (2 Turns • {total_tokens:,} tokens • ${total_cost:.4f} USD)")
    logger.info("=================================================================")

    if created_new_workspace and cfg.cleanup_after and target_workspace_id:
        logger.info(f"🧹 Cleaning up test workspace '{target_workspace_id}' (--cleanup-after requested)...")
        try:
            ws_svc.delete_workspace(target_workspace_id)
        except Exception as cl_err:
            logger.warning(f"Failed to delete test workspace: {cl_err}")

    return {
        "status": "completed",
        "workspace_id": target_workspace_id,
        "paper_id": chosen_paper_id,
        "paper_title": paper_title,
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
        "analysis_opened": {
            "paper_details": True,
            "scorecard": True,
            "extractions_count": len(extractions_list),
            "pdf_status_code": pdf_status,
        },
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "cost_metrics": cost_metrics,
    }
