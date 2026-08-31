"""
Concurrent Autonomous Agents Load & Concurrency Scenario.
"""

import logging
import random
import time
from typing import Dict, Any, Optional, List
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    AgentService,
)

logger = logging.getLogger("e2e_concurrent_load")


def run_concurrent_agents_load_scenario(config: Optional[E2EConfig] = None, num_agents: int = 2) -> Dict[str, Any]:
    """
    Validates concurrency, Celery queue scheduling, and database row-locking under parallel load:
    1. Provisions multiple independent test workspaces.
    2. Launches autonomous research agent processes in parallel across all workspaces.
    3. Monitors all agents concurrently, ensuring zero database deadlocks (select_for_update).
    4. Validates that all concurrent agent processes reach 'completed' state.
    """
    cfg = config or E2EConfig.from_env()
    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)

    logger.info("=================================================================")
    logger.info(f"⚡ STARTING CONCURRENT AGENTS LOAD SCENARIO ({num_agents} PARALLEL AGENTS)")
    logger.info(f"📍 Target Environment : {cfg.target_env.upper()} ({cfg.base_url})")
    logger.info("=================================================================")

    workspaces: List[Dict[str, Any]] = []
    processes: List[Dict[str, Any]] = []

    try:
        # 1. Provision multiple workspaces
        for i in range(1, num_agents + 1):
            rand = random.randint(10000000, 99999999)
            ws_name = f"test_e2e_concurrent_{i}_{rand}"
            ws = ws_svc.create_workspace(
                name=ws_name,
                abstract_acceptance_criteria="Accept machine learning optimization algorithms.",
                abstract_rejection_criteria="Reject unrelated biology topics.",
                full_text_acceptance_criteria="Accept computational and empirical evaluations.",
                full_text_rejection_criteria="Reject papers with zero technical discussion.",
                screening_llm_model="google/gemini-3.7-flash",
            )
            ws_svc.create_scraper(
                workspace_id=ws["id"],
                provider="arxiv",
                search_query=f'cat:cs.AI AND all:"optimization {i}"',
                limit=3,
            )
            workspaces.append(ws)

        # 2. Launch all agents concurrently
        logger.info(f"🚀 Launching {num_agents} autonomous agents simultaneously...")
        for ws in workspaces:
            proc = agent_svc.start_research_agent(
                workspace_id=ws["id"],
                name=f"Parallel Agent Run - {ws['name']}",
                limit=3,
            )
            processes.append(proc)
            logger.info(f"   • Dispatched Agent '{proc['id']}' in Workspace '{ws['name']}'")

        # 3. Monitor and poll all processes concurrently
        t0 = time.time()
        timeout = cfg.max_timeout_sec
        finished_processes = {}

        logger.info(f"⏳ Monitoring {len(processes)} parallel agent processes...")
        while len(finished_processes) < len(processes) and (time.time() - t0 < timeout):
            for p in processes:
                p_id = p["id"]
                if p_id in finished_processes:
                    continue
                status_data = agent_svc.get_agent_status(p_id)
                st = status_data.get("status")
                step = status_data.get("current_step")

                if st in ("completed", "failed", "aborted"):
                    elapsed = int(time.time() - t0)
                    logger.info(f"  🏁 Agent '{p_id}' reached terminal status '{st}' at step '{step}' in {elapsed}s")
                    finished_processes[p_id] = status_data

            time.sleep(3.0)

        # 4. Assert all finished successfully
        assert len(finished_processes) == len(processes), f"Timed out waiting for parallel agents ({len(finished_processes)}/{len(processes)} completed)"
        for p_id, p_data in finished_processes.items():
            assert p_data.get("status") == "completed", f"Agent '{p_id}' failed: {p_data}"

        total_elapsed = time.time() - t0
        logger.info("=================================================================")
        logger.info(f"🎉 CONCURRENT LOAD SCENARIO PASSED ({num_agents} agents completed in {total_elapsed:.1f}s)!")
        logger.info("=================================================================")

        tot_p_in = 0
        tot_p_out = 0
        tot_p_tok = 0
        tot_p_usd = 0.0

        for p_id, p_data in finished_processes.items():
            pr_id = p_data.get("pipeline_run")
            if pr_id:
                try:
                    pr_info = pipeline_svc.get_pipeline_run(pr_id)
                    p_in = pr_info.get("tokens_in", 0) or 0
                    p_out = pr_info.get("tokens_out", 0) or 0
                    p_tok = pr_info.get("tokens_consumed", 0) or (p_in + p_out)
                    p_usd = float(pr_info.get("usd_cost") or 0.0)
                    tot_p_in += p_in
                    tot_p_out += p_out
                    tot_p_tok += p_tok
                    tot_p_usd += p_usd
                except Exception:
                    pass

        cost_metrics = {
            "pipeline_tokens_in": tot_p_in,
            "pipeline_tokens_out": tot_p_out,
            "pipeline_total_tokens": tot_p_tok,
            "pipeline_usd_cost": tot_p_usd,
            "total_tokens_consumed": tot_p_tok,
            "total_usd_spent": tot_p_usd,
        }

        return {
            "status": "passed",
            "agents_count": len(processes),
            "total_elapsed_seconds": total_elapsed,
            "workspaces": [ws["id"] for ws in workspaces],
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            for ws in workspaces:
                try:
                    ws_svc.delete_workspace(ws["id"])
                except Exception as del_err:
                    logger.warning(f"Could not delete concurrent test workspace '{ws['id']}': {del_err}")
