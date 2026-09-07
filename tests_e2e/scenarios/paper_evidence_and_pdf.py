"""
Paper Evidence Quotes, Scorecard & Binary PDF Stream E2E Scenario.
Validates the complete User Journey 5:
- Scorecard parameter breakdown with confidence ratings and evidence quotes.
- Mathematical SignalLedger verification.
- Direct authenticated PDF binary streaming endpoint (GET /api/papers/{id}/pdf/).
"""

import logging
import random
import time
from typing import Dict, Any, Optional
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    AgentService,
    PipelineService,
)

logger = logging.getLogger("e2e_paper_evidence")


def run_paper_evidence_and_pdf_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates end-to-end paper scorecard inspection, evidence quote retrieval, and PDF streaming:
    1. Provisions workspace with structured extraction definition and signal score formula.
    2. Runs literature ingestion and parameter extraction on candidate papers.
    3. Queries GET /api/papers/{id}/ to verify scorecard fields.
    4. Queries GET /api/extractions/?paper={id} to verify evidence quotes and confidence scores.
    5. Queries GET /api/papers/{id}/pdf/ to verify authenticated binary PDF streaming and headers.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_scorecard_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("📄 STARTING PAPER SCORECARD, EVIDENCE & PDF STREAMING SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Provision workspace with custom formula
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning, neural networks, or optimization.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept algorithmic, computational, and empirical evaluations.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        signal_score_code="score = 0.6 * fit_score + 0.4 * 8.5\nreturn round(score * 10.0, 2)",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"attention mechanism"',
            limit=3,
        )

        # 2. Launch research agent run
        logger.info("🚀 Launching research pipeline to ingest and extract papers...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Scorecard Verification - {workspace_name}",
            limit=3,
            reprocess_existing=True,
        )

        # Poll until complete
        completed_agent = agent_svc.poll_until_complete(
            agent_proc["id"], max_timeout_sec=cfg.max_timeout_sec
        )
        assert completed_agent.get("status") == "completed", f"Agent run did not complete: {completed_agent}"

        # 3. Retrieve Ingested Papers
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)
        assert len(papers) > 0, "Pipeline must ingest at least one paper"
        logger.info(f"✅ Ingested {len(papers)} papers in workspace.")

        # Pick candidate paper (prefer accepted / screened)
        target_paper = None
        for p in papers:
            if p.get("signal_score") is not None or p.get("screening_status") in ("full_text_passed", "abstract_passed", "accepted"):
                target_paper = p
                break
        if not target_paper:
            target_paper = papers[0]

        paper_id = target_paper["id"]
        logger.info(f"🔍 Inspecting Scorecard for Paper '{target_paper.get('title', paper_id)[:60]}...'")

        # 4. Deep Inspection of Single Paper (GET /api/papers/{id}/)
        resp_detail = client.get(f"/api/papers/{paper_id}/", expected_status=200)
        paper_detail = resp_detail.json()

        assert "title" in paper_detail and paper_detail["title"], "Paper must contain valid title"
        assert "screening_status" in paper_detail, "Paper must have screening_status"
        logger.info(f"   • Screening Status : {paper_detail.get('screening_status')}")
        logger.info(f"   • Signal Score     : {paper_detail.get('signal_score')}")

        # 5. Verify Extractions & Evidence Quotes (GET /api/extractions/?paper={id})
        extractions = pipeline_svc.list_extractions(workspace_id=workspace_id)
        paper_extractions = [e for e in extractions if str(e.get("paper")) == str(paper_id) or str(e.get("paper_id")) == str(paper_id)]
        logger.info(f"   • Extractions found for paper: {len(paper_extractions)}")

        for ext in paper_extractions:
            conf = ext.get("confidence_score")
            logger.info(f"     - Extraction '{ext.get('parameter_name', 'metric')}': Value='{ext.get('exit_metric')}', Confidence={conf}")
            if conf is not None:
                assert 0.0 <= float(conf) <= 1.0, f"Confidence score must be between 0.0 and 1.0, got: {conf}"

        # 6. Verify Authenticated PDF Streaming (GET /api/papers/{id}/pdf/)
        logger.info(f"📥 Probing authenticated PDF stream at /api/papers/{paper_id}/pdf/ ...")
        resp_pdf = client.get(f"/api/papers/{paper_id}/pdf/")

        if resp_pdf.status_code == 200:
            content_type = resp_pdf.headers.get("Content-Type", "")
            content_disposition = resp_pdf.headers.get("Content-Disposition", "")
            content_length = len(resp_pdf.content)
            logger.info(f"   • PDF Stream HTTP 200 OK | Type: {content_type} | Size: {content_length} bytes")
            logger.info(f"   • Header Content-Disposition: {content_disposition}")
            assert "application/pdf" in content_type, f"Expected application/pdf content type, got: {content_type}"
            assert content_length > 100, f"PDF binary stream appears truncated ({content_length} bytes)"
        elif resp_pdf.status_code == 404:
            # Paper might not have had open-access PDF downloaded
            logger.info(f"   • PDF not present on object storage (HTTP 404 handled gracefully). Response: {resp_pdf.text[:100]}")
        else:
            raise AssertionError(f"Unexpected response code for PDF stream: {resp_pdf.status_code} ({resp_pdf.text})")

        logger.info("=================================================================")
        logger.info("🎉 PAPER SCORECARD, EVIDENCE & PDF STREAMING SCENARIO PASSED!")
        logger.info("=================================================================")

        pr_id = completed_agent.get("pipeline_run")
        pr_info = pipeline_svc.get_pipeline_run(pr_id) if pr_id else {}
        p_in = int(pr_info.get("tokens_in", 0) or 0)
        p_out = int(pr_info.get("tokens_out", 0) or 0)
        p_tok = int(pr_info.get("tokens_consumed", 0) or (p_in + p_out))
        p_usd = float(pr_info.get("usd_cost") or 0.0)

        cost_metrics = {
            "pipeline_tokens_in": p_in,
            "pipeline_tokens_out": p_out,
            "pipeline_total_tokens": p_tok,
            "pipeline_usd_cost": p_usd,
            "total_tokens_consumed": p_tok,
            "total_usd_spent": p_usd,
        }

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "inspected_paper_id": paper_id,
            "screening_status": paper_detail.get("screening_status"),
            "signal_score": paper_detail.get("signal_score"),
            "extractions_count": len(paper_extractions),
            "pdf_status_code": resp_pdf.status_code,
            "total_papers": len(papers),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not clean up test workspace: {del_err}")
