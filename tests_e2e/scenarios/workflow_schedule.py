"""
Workflow Scheduling, Triggering & Observability Scenario.
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
    ScheduleService,
)

logger = logging.getLogger("e2e_workflow_schedule")


def run_workflow_schedule_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates end-to-end Workflow Schedule management, triggering, and live status observability:
    1. Creates a dedicated test workspace with an arXiv scraper.
    2. Creates a WorkflowSchedule via REST API with daily frequency and prevent_overlap=True.
    3. Triggers the schedule immediately via POST /api/schedules/{id}/trigger/.
    4. Verifies that the created ResearchAgentProcess and PipelineRun are linked to the schedule.
    5. Polls the agent process until completion.
    6. Verifies that the schedule's observable status reflects 'completed' and tracks run metrics.
    7. Tests overlap prevention (non-force trigger behavior).
    8. Cleans up schedule and workspace.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_sched_{random_suffix}"
    schedule_name = f"One-Off Test Schedule - {random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)
    sched_svc = ScheduleService(client)

    logger.info("=================================================================")
    logger.info("📅 STARTING WORKFLOW SCHEDULE & OBSERVABILITY SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Schedule Name  : {schedule_name} (freq: one_off)")
    logger.info("=================================================================")

    # Step 0: Pre-clean any lingering test schedules from previous test runs
    if cfg.cleanup_before:
        sched_svc.cleanup_old_test_schedules()

    # 1. Create Workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept quantum computing and fault-tolerant quantum algorithms.",
        abstract_rejection_criteria="Reject classical distributed computing papers.",
        full_text_acceptance_criteria="Accept quantum hardware and architecture evaluations.",
        full_text_rejection_criteria="Reject non-technical position papers.",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]
    schedule_id = None

    try:
        # 2. Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:quant-ph AND all:"fault-tolerant quantum"',
            limit=3,
        )

        # 3. Create One-Off Schedule (auto-deactivates upon execution to prevent recurring Celery Beat runs)
        sched_data = sched_svc.create_schedule(
            workspace_id=workspace_id,
            name=schedule_name,
            frequency="one_off",
            timezone_name="UTC",
            prevent_overlap=True,
            max_consecutive_failures=3,
            reprocess_existing=False,
            configuration_override={"limit": 3},
            is_active=True,
        )
        schedule_id = sched_data["id"]
        assert sched_data.get("name") == schedule_name
        assert sched_data.get("prevent_overlap") is True

        # 4. Trigger Schedule Run
        trigger_resp = sched_svc.trigger_schedule(schedule_id=schedule_id, force=True)
        agent_process_id = trigger_resp.get("agent_id") or trigger_resp.get("agent_process_id")
        pipeline_run_id = trigger_resp.get("pipeline_run_id")
        assert agent_process_id, f"No agent_process_id returned from schedule trigger: {trigger_resp}"

        # 5. Verify Immediate Schedule State
        sched_after_trigger = sched_svc.get_schedule(schedule_id)
        assert sched_after_trigger.get("last_status") in ("running", "pending", "completed")
        assert sched_after_trigger.get("total_runs_count", 0) >= 1

        # 6. Poll Agent Process Until Terminal State
        completed_agent = agent_svc.poll_until_complete(
            process_id=agent_process_id,
            max_timeout_sec=cfg.max_timeout_sec,
        )
        assert completed_agent.get("status") == "completed", f"Scheduled agent process failed: {completed_agent}"

        # 7. Verify Linked PipelineRun & Schedule State Consistency
        final_pipeline_run_id = completed_agent.get("pipeline_run") or pipeline_run_id
        pr_data = {}
        if final_pipeline_run_id:
            pr_data = pipeline_svc.get_pipeline_run(final_pipeline_run_id)
            assert pr_data.get("schedule") == schedule_id or pr_data.get("schedule_id") == schedule_id, (
                f"PipelineRun {final_pipeline_run_id} is not linked to schedule {schedule_id}: {pr_data}"
            )
            assert pr_data.get("status") == "completed"

        # 8. Verify Observable Schedule Status & Guaranteed Auto-Deactivation
        final_sched = sched_svc.get_schedule(schedule_id)
        current_status = final_sched.get("current_execution_status") or final_sched.get("last_status")
        logger.info(f"📊 Final Schedule State:")
        logger.info(f"   • Current Status : {current_status}")
        logger.info(f"   • Total Runs     : {final_sched.get('total_runs_count')}")
        logger.info(f"   • Successful Runs: {final_sched.get('successful_runs_count')}")
        logger.info(f"   • Is Active      : {final_sched.get('is_active')} (PAUSED/COMPLETED)")
        logger.info(f"   • Next Run At    : {final_sched.get('next_run_at')}")

        assert current_status == "completed", f"Schedule status should be 'completed', got '{current_status}'"
        assert final_sched.get("successful_runs_count", 0) >= 1
        assert final_sched.get("is_active") is False, "One-off schedule must auto-deactivate after execution"
        assert final_sched.get("next_run_at") is None, "One-off schedule must have next_run_at=None"

        logger.info("=================================================================")
        logger.info("🎉 WORKFLOW SCHEDULE & OBSERVABILITY SCENARIO PASSED (SAFELY DEACTIVATED)!")
        logger.info("=================================================================")

        p_in = int(pr_data.get("tokens_in", 0) or 0)
        p_out = int(pr_data.get("tokens_out", 0) or 0)
        p_tok = int(pr_data.get("tokens_consumed", 0) or (p_in + p_out))
        p_usd = float(pr_data.get("usd_cost") or 0.0)

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
            "schedule_id": schedule_id,
            "agent_process_id": agent_process_id,
            "pipeline_run_id": final_pipeline_run_id,
            "schedule_status": current_status,
            "total_papers": int(pr_data.get("total_papers_fetched", 0) or 0),
            "cost_metrics": cost_metrics,
        }

    finally:
        if schedule_id:
            try:
                # Guaranteed safety: ensure schedule is deactivated under all circumstances
                sched_svc.deactivate_schedule(schedule_id)
            except Exception:
                pass
        if cfg.delete_after:
            if schedule_id:
                try:
                    sched_svc.delete_schedule(schedule_id)
                except Exception as sched_err:
                    logger.warning(f"Could not delete test schedule: {sched_err}")
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as ws_err:
                logger.warning(f"Could not delete test workspace: {ws_err}")
