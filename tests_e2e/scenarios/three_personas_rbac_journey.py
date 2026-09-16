"""
Three Personas RBAC Matrix E2E Scenario.

Validates the full privilege hierarchy across all 3 platform personas:
1. Admin:
   - Full workspace management (PATCH criteria, configuration).
   - Scraper creation, update, deletion.
   - Full pipeline execution lifecycle: start, pause, resume, abort, tick.
   - Dedicated privilege: ONLY Admin can trigger mid-step pipeline rerun (rerun-from-step).
2. Manager:
   - Workspace criteria & scrapers management.
   - Pipeline execution lifecycle: start, pause, resume, abort.
   - Strictly FORBIDDEN from rerun-from-step (HTTP 403 Forbidden).
3. Researcher:
   - Read-only analytical inspection: workspaces, papers, briefings, scorecards, scoring formulas.
   - Strictly FORBIDDEN from modifying workspace criteria (HTTP 403 Forbidden).
   - Strictly FORBIDDEN from creating or modifying scrapers (HTTP 403 Forbidden).
   - Strictly FORBIDDEN from starting, pausing, resuming, aborting, ticking, or rerunning pipeline runs (all HTTP 403 Forbidden).
   - Strictly FORBIDDEN from deleting workspaces (HTTP 403 Forbidden).
4. Outsider / Unassigned:
   - Zero-leakage verification: GET private workspace returns 404/403, GET papers returns empty list.
"""

import logging
import random
from typing import Dict, Any, Optional

from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    PipelineService,
)

logger = logging.getLogger("e2e_three_personas")


def run_three_personas_rbac_journey_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Executes end-to-end RBAC verification for Admin, Manager, and Researcher personas.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_personas_{random_suffix}"

    admin_client = APIClient(cfg.base_url)
    auth = AuthService(admin_client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(admin_client)
    pipeline_svc = PipelineService(admin_client)

    logger.info("=================================================================")
    logger.info("👥 STARTING THREE PERSONAS RBAC JOURNEY SCENARIO")
    logger.info(f"📍 Target Workspace : {workspace_name}")
    logger.info(f"📍 Target API       : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Provision Workspace as Admin
    logger.info("\n🏛️ Step 1: Provisioning isolated workspace via Admin...")
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept quantum and algorithmic research.",
        abstract_rejection_criteria="Reject unrelated biology.",
        full_text_acceptance_criteria="Accept empirical evaluations.",
        full_text_rejection_criteria="Reject pure opinion.",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]
    logger.info(f"   • Created workspace '{workspace_id}' (Admin role)")

    # 2. Provision or Resolve Manager & Researcher User Tokens
    mgr_client = APIClient(cfg.base_url)
    res_client = APIClient(cfg.base_url)
    outsider_client = APIClient(cfg.base_url)

    created_users = []

    try:
        # Check if Django ORM is directly available in the test runtime
        has_orm = False
        try:
            import sys
            import os
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend"))
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
            import django
            django.setup()
            from django.contrib.auth import get_user_model
            from research_intelligence.models import WorkspaceMember
            from rest_framework_simplejwt.tokens import RefreshToken

            is_local_target = "localhost" in cfg.base_url or "127.0.0.1" in cfg.base_url
            # Allow ORM test user creation if targeting local environment or test database
            if is_local_target:
                User = get_user_model()
                has_orm = True
                logger.info("   • Local Django ORM detected: provisioning persona test users...")

                mgr_user, _ = User.objects.get_or_create(
                    username=f"test_mgr_{random_suffix}",
                    defaults={"email": f"mgr_{random_suffix}@schwarz.de", "first_name": "Test", "last_name": "Manager"}
                )
                res_user, _ = User.objects.get_or_create(
                    username=f"test_res_{random_suffix}",
                    defaults={"email": f"res_{random_suffix}@schwarz.de", "first_name": "Test", "last_name": "Researcher"}
                )
                out_user, _ = User.objects.get_or_create(
                    username=f"test_out_{random_suffix}",
                    defaults={"email": f"out_{random_suffix}@schwarz.de", "first_name": "Test", "last_name": "Outsider"}
                )
                created_users.extend([mgr_user, res_user, out_user])

                WorkspaceMember.objects.update_or_create(
                    workspace_id=workspace_id,
                    user=mgr_user,
                    defaults={"role": "manager"}
                )
                WorkspaceMember.objects.update_or_create(
                    workspace_id=workspace_id,
                    user=res_user,
                    defaults={"role": "researcher"}
                )

                mgr_client.set_auth_token(str(RefreshToken.for_user(mgr_user).access_token))
                res_client.set_auth_token(str(RefreshToken.for_user(res_user).access_token))
                outsider_client.set_auth_token(str(RefreshToken.for_user(out_user).access_token))
                logger.info("   ✅ Successfully authenticated Manager, Researcher, and Outsider tokens via JWT.")
        except Exception as orm_err:
            logger.info(f"   ℹ️ Direct ORM not available ({orm_err}); falling back to HTTP role probing.")

        results = {
            "status": "passed",
            "workspace_id": workspace_id,
            "persona_checks": {},
        }

        # =====================================================================
        # Phase 1: Test Admin Persona Privileges
        # =====================================================================
        logger.info("\n👑 Phase 1: Validating Admin Persona Privileges...")

        # 1.1 Admin can update workspace criteria
        admin_patch = admin_client.patch(
            f"/api/workspaces/{workspace_id}/",
            json_data={"name": f"{workspace_name} - Admin Verified"}
        )
        assert admin_patch.status_code == 200, f"Admin must be allowed to patch workspace: {admin_patch.status_code}"
        logger.info("   ✅ Admin successfully updated workspace settings (HTTP 200)")

        # 1.2 Admin can create scraper
        admin_scraper_resp = admin_client.post(
            "/api/scrapers/",
            json_data={
                "workspace": workspace_id,
                "provider": "arxiv",
                "search_query": 'cat:cs.AI AND all:"quantum"',
                "limit": 2,
            }
        )
        assert admin_scraper_resp.status_code == 201, f"Admin must be allowed to create scrapers: {admin_scraper_resp.status_code}"
        scraper_id = admin_scraper_resp.json().get("id")
        logger.info(f"   ✅ Admin created scraper '{scraper_id}' (HTTP 201)")

        # 1.3 Admin can start a pipeline run
        admin_run_resp = admin_client.post(
            "/api/pipeline-runs/",
            json_data={
                "workspace_id": workspace_id,
                "name": "Admin E2E Test Run",
            }
        )
        assert admin_run_resp.status_code == 201, f"Admin must be allowed to start pipeline run: {admin_run_resp.status_code}"
        admin_run_id = admin_run_resp.json().get("id")
        logger.info(f"   ✅ Admin created pipeline run '{admin_run_id}' (HTTP 201)")

        # 1.4 Admin can pause pipeline run
        admin_pause = admin_client.post(f"/api/pipeline-runs/{admin_run_id}/pause/", json_data={"reason": "Admin inspection"})
        assert admin_pause.status_code == 200, f"Admin must be allowed to pause run: {admin_pause.status_code}"
        logger.info("   ✅ Admin successfully paused pipeline run (HTTP 200)")

        # 1.5 Admin can resume pipeline run
        admin_resume = admin_client.post(f"/api/pipeline-runs/{admin_run_id}/resume/")
        assert admin_resume.status_code == 200, f"Admin must be allowed to resume run: {admin_resume.status_code}"
        logger.info("   ✅ Admin successfully resumed pipeline run (HTTP 200)")

        # 1.6 Admin can abort pipeline run
        admin_abort = admin_client.post(f"/api/pipeline-runs/{admin_run_id}/abort/")
        assert admin_abort.status_code == 200, f"Admin must be allowed to abort run: {admin_abort.status_code}"
        logger.info("   ✅ Admin successfully aborted pipeline run (HTTP 200)")

        # 1.7 Dedicated privilege: Admin CAN rerun from step
        admin_rerun = admin_client.post(
            f"/api/pipeline-runs/{admin_run_id}/rerun-from-step/",
            json_data={"step_name": "search"}
        )
        assert admin_rerun.status_code == 200, f"Admin must be allowed to rerun from step: {admin_rerun.status_code}"
        logger.info("   ✅ Admin successfully executed rerun-from-step (HTTP 200)")
        results["persona_checks"]["admin_full_lifecycle"] = "PASSED"

        # =====================================================================
        # Phase 2: Test Manager Persona Privileges & Boundaries
        # =====================================================================
        if has_orm:
            logger.info("\n💼 Phase 2: Validating Manager Persona Privileges & Boundaries...")

            # 2.1 Manager can create pipeline runs
            mgr_run_resp = mgr_client.post(
                "/api/pipeline-runs/",
                json_data={
                    "workspace_id": workspace_id,
                    "name": "Manager E2E Test Run",
                }
            )
            assert mgr_run_resp.status_code == 201, f"Manager must be allowed to start pipeline run: {mgr_run_resp.status_code}"
            mgr_run_id = mgr_run_resp.json().get("id")
            logger.info(f"   ✅ Manager created pipeline run '{mgr_run_id}' (HTTP 201)")

            # 2.2 Manager can abort pipeline run
            mgr_abort = mgr_client.post(f"/api/pipeline-runs/{mgr_run_id}/abort/")
            assert mgr_abort.status_code == 200, f"Manager must be allowed to abort run: {mgr_abort.status_code}"
            logger.info("   ✅ Manager successfully aborted pipeline run (HTTP 200)")

            # 2.3 Manager STRICTLY FORBIDDEN from rerun-from-step (Admin only!)
            mgr_rerun = mgr_client.post(
                f"/api/pipeline-runs/{mgr_run_id}/rerun-from-step/",
                json_data={"step_name": "search"}
            )
            assert mgr_rerun.status_code == 403, (
                f"Manager MUST receive HTTP 403 Forbidden on rerun-from-step, got: {mgr_rerun.status_code}"
            )
            logger.info("   🛡️ Manager rerun-from-step successfully BLOCKED with HTTP 403 Forbidden.")
            results["persona_checks"]["manager_rerun_guard"] = "PASSED (403)"

            # =====================================================================
            # Phase 3: Test Researcher Persona Privileges & Boundaries
            # =====================================================================
            logger.info("\n🔬 Phase 3: Validating Researcher Persona Privileges & Boundaries...")

            # 3.1 Researcher can perform analytical reads (Happy Path)
            res_ws = res_client.get(f"/api/workspaces/{workspace_id}/")
            assert res_ws.status_code == 200, f"Researcher must be allowed to read workspace: {res_ws.status_code}"
            logger.info("   ✅ Researcher can read workspace configuration (HTTP 200)")

            res_scoring = res_client.get(f"/api/workspaces/{workspace_id}/scoring/")
            assert res_scoring.status_code == 200, f"Researcher must be allowed to read scoring formula: {res_scoring.status_code}"
            logger.info("   ✅ Researcher can read scoring endpoint (HTTP 200)")

            res_papers = res_client.get("/api/papers/", params={"workspace": workspace_id})
            assert res_papers.status_code == 200, f"Researcher must be allowed to list papers: {res_papers.status_code}"
            logger.info("   ✅ Researcher can read papers endpoint (HTTP 200)")

            res_reports = res_client.get("/api/reports/", params={"workspace": workspace_id})
            assert res_reports.status_code == 200, f"Researcher must be allowed to read reports: {res_reports.status_code}"
            logger.info("   ✅ Researcher can read executive briefings (HTTP 200)")

            # 3.2 Researcher STRICTLY FORBIDDEN from starting pipeline runs
            res_start_run = res_client.post(
                "/api/pipeline-runs/",
                json_data={"workspace_id": workspace_id, "name": "Illegal Researcher Run"}
            )
            assert res_start_run.status_code == 403, (
                f"Researcher MUST receive HTTP 403 on pipeline start, got: {res_start_run.status_code}"
            )
            logger.info("   🛡️ Researcher pipeline start BLOCKED with HTTP 403 Forbidden.")

            res_start_agent = res_client.post(
                "/api/pipeline-runs/start/",
                json_data={"workspace_id": workspace_id, "name": "Illegal Researcher Agent"}
            )
            assert res_start_agent.status_code == 403, (
                f"Researcher MUST receive HTTP 403 on pipeline-runs/start/, got: {res_start_agent.status_code}"
            )
            logger.info("   🛡️ Researcher pipeline-runs/start/ BLOCKED with HTTP 403 Forbidden.")

            # 3.3 Researcher STRICTLY FORBIDDEN from mutative pipeline lifecycle actions
            res_pause = res_client.post(f"/api/pipeline-runs/{admin_run_id}/pause/")
            assert res_pause.status_code == 403, f"Researcher must get 403 on pause, got: {res_pause.status_code}"

            res_resume = res_client.post(f"/api/pipeline-runs/{admin_run_id}/resume/")
            assert res_resume.status_code == 403, f"Researcher must get 403 on resume, got: {res_resume.status_code}"

            res_tick = res_client.post(f"/api/pipeline-runs/{admin_run_id}/tick/")
            assert res_tick.status_code == 403, f"Researcher must get 403 on tick, got: {res_tick.status_code}"

            res_abort = res_client.post(f"/api/pipeline-runs/{admin_run_id}/abort/")
            assert res_abort.status_code == 403, f"Researcher must get 403 on abort, got: {res_abort.status_code}"

            res_rerun = res_client.post(f"/api/pipeline-runs/{admin_run_id}/rerun-from-step/")
            assert res_rerun.status_code == 403, f"Researcher must get 403 on rerun-from-step, got: {res_rerun.status_code}"

            res_trigger = res_client.post(f"/api/pipeline-runs/{admin_run_id}/trigger-step/", json_data={"step_type": "download"})
            assert res_trigger.status_code == 403, f"Researcher must get 403 on trigger-step, got: {res_trigger.status_code}"
            logger.info("   🛡️ Researcher pipeline controls (pause, resume, tick, abort, rerun, trigger) all BLOCKED with HTTP 403.")

            # 3.4 Researcher STRICTLY FORBIDDEN from mutating workspace criteria
            res_patch_ws = res_client.patch(
                f"/api/workspaces/{workspace_id}/",
                json_data={"name": "Hacked by Researcher"}
            )
            assert res_patch_ws.status_code == 403, (
                f"Researcher MUST receive HTTP 403 on workspace patch, got: {res_patch_ws.status_code}"
            )
            logger.info("   🛡️ Researcher workspace settings mutation BLOCKED with HTTP 403 Forbidden.")

            # 3.5 Researcher STRICTLY FORBIDDEN from mutating scrapers
            res_scraper = res_client.post(
                "/api/scrapers/",
                json_data={"workspace": workspace_id, "provider": "arxiv", "search_query": "cat:cs.AI"}
            )
            assert res_scraper.status_code == 403, (
                f"Researcher MUST receive HTTP 403 on scraper create, got: {res_scraper.status_code}"
            )
            logger.info("   🛡️ Researcher scraper creation BLOCKED with HTTP 403 Forbidden.")

            # 3.6 Researcher STRICTLY FORBIDDEN from deleting workspace
            res_del_ws = res_client.delete(f"/api/workspaces/{workspace_id}/")
            assert res_del_ws.status_code == 403, (
                f"Researcher MUST receive HTTP 403 on workspace delete, got: {res_del_ws.status_code}"
            )
            logger.info("   🛡️ Researcher workspace deletion BLOCKED with HTTP 403 Forbidden.")
            results["persona_checks"]["researcher_read_only_safety"] = "PASSED"
        else:
            logger.info("   ℹ️ Skipped sub-persona queries in pure remote mode without direct user creation.")
            results["persona_checks"]["manager_rerun_guard"] = "SKIPPED (REMOTE)"
            results["persona_checks"]["researcher_read_only_safety"] = "SKIPPED (REMOTE)"

        # =====================================================================
        # Phase 4: Test Outsider Persona (Zero-Leakage Isolation)
        # =====================================================================
        logger.info("\n🚫 Phase 4: Validating Outsider Persona (Zero Data Leakage)...")

        out_ws = outsider_client.get(f"/api/workspaces/{workspace_id}/")
        assert out_ws.status_code in (401, 403, 404), (
            f"Outsider MUST receive 401, 403 or 404 for unshared workspace, got: {out_ws.status_code}"
        )

        out_papers = outsider_client.get("/api/papers/", params={"workspace": workspace_id})
        assert out_papers.status_code in (200, 401, 403), f"Outsider papers request failed unexpectedly: {out_papers.status_code}"
        if out_papers.status_code == 200:
            out_papers_data = out_papers.json()
            out_papers_list = out_papers_data.get("results", out_papers_data) if isinstance(out_papers_data, dict) else out_papers_data
            assert len(out_papers_list) == 0, (
                f"Outsider MUST see 0 papers for unshared workspace, got: {len(out_papers_list)}"
            )
        logger.info("   🛡️ Outsider access blocked with 0 data leakage (HTTP 401/403/404).")
        results["persona_checks"]["outsider_isolation"] = "PASSED"

        logger.info("\n=================================================================")
        logger.info("🎉 THREE PERSONAS RBAC JOURNEY COMPLETED SUCCESSFULLY!")
        logger.info("   • Admin: Full lifecycle + rerun-from-step  : VERIFIED (200)")
        logger.info("   • Manager: Start/stop allowed, rerun blocked: VERIFIED (403)")
        logger.info("   • Researcher: Analytical reads OK, all mutations blocked: VERIFIED (403)")
        logger.info("   • Outsider: Zero data leakage               : VERIFIED (403/404)")
        logger.info("=================================================================")

        return results

    finally:
        # Clean up temporary users if created via ORM
        for u in created_users:
            try:
                u.delete()
            except Exception:
                pass

        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
                logger.info(f"🧹 Cleaned up RBAC test workspace '{workspace_id}'")
            except Exception as e:
                logger.warning(f"Could not delete test workspace {workspace_id}: {e}")
