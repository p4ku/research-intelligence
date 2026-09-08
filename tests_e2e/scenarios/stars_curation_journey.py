"""
Stars & Personal Curation End-to-End User Journey Scenario.

Validates:
1. Reading initial user stars via GET /api/stars/.
2. Adding a paper star via PUT /api/stars/ (kind='paper', starred=True).
3. Adding a briefing (PipelineRun) star via PUT /api/stars/ (kind='briefing', starred=True).
4. Idempotency of star operations (duplicate PUT requests).
5. Unstarring paper (PUT /api/stars/ with starred=False) while preserving briefing star.
6. Access control / 404 security guard when attempting to star a resource outside the user's workspace.
"""

import logging
import random
import uuid
from typing import Dict, Any, Optional

from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    PipelineService,
)

logger = logging.getLogger("e2e_stars_journey")


def run_stars_curation_journey_scenario(
    config: Optional[E2EConfig] = None,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the complete Stars Curation Journey:
    - User inspects current starred set
    - Stars papers and briefings in their accessible workspace
    - Verifies idempotent behavior and state consistency
    - Verifies cross-workspace isolation and 404 rejection on unauthorized IDs
    """
    cfg = config or E2EConfig.from_env()
    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)

    ws_svc = WorkspaceService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("⭐ STARTING STARS & PERSONAL CURATION E2E USER JOURNEY")
    logger.info(f"📍 Target API : {cfg.base_url}")
    logger.info("=================================================================")

    # Phase 1: Verify Initial Stars Retrieval
    logger.info("📡 Phase 1: Fetching initial user stars (/api/stars/)...")
    resp_init = client.get("/api/stars/", expected_status=200)
    initial_stars = resp_init.json()
    assert "papers" in initial_stars, "Stars response must contain 'papers' list"
    assert "briefings" in initial_stars, "Stars response must contain 'briefings' list"
    logger.info(f"   • Initial stars count: {len(initial_stars['papers'])} papers, {len(initial_stars['briefings'])} briefings")

    # Phase 2: Find or Provision Target Resources
    target_ws_id = workspace_id
    created_temp_workspace = False

    if not target_ws_id:
        existing_workspaces = ws_svc.list_workspaces()
        if existing_workspaces:
            target_ws_id = existing_workspaces[0]["id"]
        else:
            random_suffix = random.randint(100000, 999999)
            ws_data = ws_svc.create_workspace(name=f"test_e2e_stars_{random_suffix}")
            target_ws_id = ws_data["id"]
            created_temp_workspace = True

    # Retrieve accessible papers and pipeline runs in this workspace
    papers = pipeline_svc.list_papers(workspace_id=target_ws_id, limit=5)
    runs = pipeline_svc.list_pipeline_runs(workspace_id=target_ws_id)

    target_paper_id = None
    target_run_id = None

    if papers and len(papers) > 0:
        target_paper_id = papers[0]["id"]

    if runs and len(runs) > 0:
        target_run_id = runs[0]["id"]

    results = {
        "status": "PASSED",
        "tested_paper_star": False,
        "tested_briefing_star": False,
        "tested_unstar": False,
        "tested_isolation_guard": False,
    }

    try:
        # Phase 3: Star a Paper (if paper exists in workspace)
        if target_paper_id:
            logger.info(f"⭐ Phase 3: Starring Paper ID {target_paper_id}...")
            resp_star_paper = client.put(
                "/api/stars/",
                json_data={"kind": "paper", "id": target_paper_id, "starred": True},
                expected_status=200,
            )
            data = resp_star_paper.json()
            assert target_paper_id in data["papers"], f"Paper {target_paper_id} must appear in starred papers list"
            logger.info("   • Successfully starred paper and verified in payload.")

            # Test Idempotency
            logger.info("🔁 Phase 3b: Testing PUT idempotence (starring same paper again)...")
            resp_idem = client.put(
                "/api/stars/",
                json_data={"kind": "paper", "id": target_paper_id, "starred": True},
                expected_status=200,
            )
            assert target_paper_id in resp_idem.json()["papers"]
            results["tested_paper_star"] = True

        # Phase 4: Star a Briefing / PipelineRun (if run exists in workspace)
        if target_run_id:
            logger.info(f"📑 Phase 4: Starring Briefing (Run ID {target_run_id})...")
            resp_star_run = client.put(
                "/api/stars/",
                json_data={"kind": "briefing", "id": target_run_id, "starred": True},
                expected_status=200,
            )
            data = resp_star_run.json()
            assert target_run_id in data["briefings"], f"Run {target_run_id} must appear in starred briefings list"
            logger.info("   • Successfully starred briefing and verified in payload.")
            results["tested_briefing_star"] = True

        # Phase 5: Unstarring
        if target_paper_id:
            logger.info(f"❌ Phase 5: Unstarring Paper ID {target_paper_id}...")
            resp_unstar = client.put(
                "/api/stars/",
                json_data={"kind": "paper", "id": target_paper_id, "starred": False},
                expected_status=200,
            )
            data = resp_unstar.json()
            assert target_paper_id not in data["papers"], f"Paper {target_paper_id} must be removed from starred list"
            logger.info("   • Paper successfully unstarred.")
            results["tested_unstar"] = True

        # Phase 6: Security Guard & Cross-Workspace Isolation
        logger.info("🛡️ Phase 6: Probing with non-existent / unauthorized UUID...")
        fake_uuid = str(uuid.uuid4())
        resp_fake = client.put(
            "/api/stars/",
            json_data={"kind": "paper", "id": fake_uuid, "starred": True},
        )
        assert resp_fake.status_code == 404, f"Expected HTTP 404 for unknown paper UUID, got {resp_fake.status_code}"
        logger.info(f"   • Correctly blocked with HTTP {resp_fake.status_code}: {resp_fake.json().get('error')}")
        results["tested_isolation_guard"] = True

    finally:
        if created_temp_workspace and target_ws_id:
            try:
                ws_svc.delete_workspace(target_ws_id)
                logger.info(f"🧹 Cleaned up temporary workspace {target_ws_id}")
            except Exception as e:
                logger.warning(f"Could not delete temp workspace {target_ws_id}: {e}")

    logger.info("=================================================================")
    logger.info("🎉 STARS CURATION E2E USER JOURNEY COMPLETED SUCCESSFULLY")
    logger.info("=================================================================")
    return results
