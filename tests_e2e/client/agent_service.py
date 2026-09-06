"""
Research Agent Process Service for E2E Tests.
"""

import logging
import time
from typing import Dict, Any, Optional
from .api_client import APIClient

logger = logging.getLogger("e2e_agent")


class AgentService:
    def __init__(self, client: APIClient):
        self.client = client

    def start_research_agent(
        self,
        workspace_id: str,
        name: str = "E2E Autonomous Literature Review",
        limit: int = 10,
        n_last_days: Optional[int] = None,
        query_prefix: Optional[str] = None,
        skip_abstract_screening: bool = False,
        reprocess_existing: bool = False,
        notification_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "workspace": workspace_id,
            "name": name,
            "limit": limit,
            "n_last_days": n_last_days,
            "query_prefix": query_prefix,
            "skip_abstract_screening": skip_abstract_screening,
            "reprocess_existing": reprocess_existing,
            "notification_email": notification_email,
        }
        logger.info(f"🚀 Launching Autonomous Research Agent in workspace '{workspace_id}' (limit: {limit})...")
        resp = self.client.post("/api/agents/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ Research Agent started! Process ID: {data.get('id')}")
        return data

    def get_agent_status(self, process_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/agents/{process_id}/", expected_status=200)
        return resp.json()

    def pause_agent(self, process_id: str) -> Dict[str, Any]:
        resp = self.client.post(f"/api/agents/{process_id}/pause/", expected_status=200)
        return resp.json()

    def resume_agent(self, process_id: str) -> Dict[str, Any]:
        resp = self.client.post(f"/api/agents/{process_id}/resume/", expected_status=200)
        return resp.json()

    def abort_agent(self, process_id: str) -> Dict[str, Any]:
        resp = self.client.post(f"/api/agents/{process_id}/abort/", expected_status=200)
        return resp.json()

    def poll_until_complete(
        self,
        process_id: str,
        max_timeout_sec: int = 900,
        poll_interval_sec: float = 3.0,
        on_step_change=None,
    ) -> Dict[str, Any]:
        """
        Polls the ResearchAgentProcess until it reaches a terminal status
        ('completed', 'failed', 'aborted'), logging real-time step progress,
        worker telemetry, and token metrics at every tick.
        """
        t0 = time.time()
        last_step = None
        pipeline_run_id = None
        logger.info(f"⏳ Monitoring Autonomous Agent Process '{process_id}' (Timeout: {max_timeout_sec}s, Poll: {poll_interval_sec}s)...")

        step_names = {
            "initialized": "Initialized",
            "search": "Search & Ingestion",
            "abstract_screening": "Abstract Screening",
            "download": "Parallel PDF Download",
            "ocr": "Layout OCR Parsing",
            "full_text_screening": "Full-Text Screening",
            "screening": "Screening",
            "extraction": "Parameter Extraction",
            "signal_score": "Composite Signal Score",
            "reporting": "Executive Narrative & Alerts",
            "completed": "Completed",
        }

        while time.time() - t0 < max_timeout_sec:
            proc = self.get_agent_status(process_id)
            current_status = proc.get("status")
            current_step = proc.get("current_step")
            elapsed = int(time.time() - t0)

            pipeline_run_id = proc.get("pipeline_run") or pipeline_run_id

            # Query live component metrics from pipeline run or stage results
            live_detail = ""
            cost_detail = ""
            stats_summary = ""

            stage_res = proc.get("stage_results") or {}
            
            # Extract cumulative stage metrics
            s_m = (stage_res.get("search") or {}).get("metrics") or {}
            a_m = (stage_res.get("abstract_screening") or {}).get("metrics") or {}
            d_m = (stage_res.get("download") or {}).get("metrics") or {}
            f_m = (stage_res.get("full_text_screening") or {}).get("metrics") or {}
            e_m = (stage_res.get("extraction") or {}).get("metrics") or {}

            parts = []
            if s_m.get("total_fetched") is not None:
                parts.append(f"Ingested: {s_m.get('total_fetched')}")
            if a_m.get("total_screened") is not None or a_m.get("passed") is not None:
                p_cnt = a_m.get('passed', 0)
                r_cnt = a_m.get('rejected', 0)
                tot = a_m.get('total_to_screen') or a_m.get('total_screened') or (p_cnt + r_cnt)
                parts.append(f"Abstract: {a_m.get('total_screened', p_cnt + r_cnt)}/{tot} (✓{p_cnt} ✗{r_cnt})")
            if d_m.get("downloaded") is not None:
                parts.append(f"PDFs: {d_m.get('downloaded') + d_m.get('cached', 0)}")
            if f_m.get("total_screened") is not None or f_m.get("passed") is not None:
                fp_cnt = f_m.get('passed', 0)
                fr_cnt = f_m.get('rejected', 0)
                parts.append(f"FullText: {f_m.get('total_screened', fp_cnt + fr_cnt)} (✓{fp_cnt} ✗{fr_cnt})")
            if e_m.get("completed_extractions") is not None or e_m.get("total_extractions") is not None:
                parts.append(f"Extractions: {e_m.get('completed_extractions', e_m.get('total_extractions', 0))}")

            if parts:
                stats_summary = " | " + " | ".join(parts)

            if pipeline_run_id:
                try:
                    pr_resp = self.client.get(f"/api/pipeline-runs/{pipeline_run_id}/")
                    if pr_resp.status_code == 200:
                        pr_data = pr_resp.json()
                        comp_runs = pr_data.get("component_runs", [])
                        running_cr = next((cr for cr in comp_runs if cr.get("status") == "running"), None)
                        if running_cr:
                            m = running_cr.get("metrics") or {}
                            if m.get("total_work_items") and m.get("completed_extractions") is not None:
                                c_ext = m.get("completed_extractions", 0)
                                f_ext = m.get("failed_extractions", 0)
                                t_ext = m.get("total_work_items", 0)
                                pct_ext = m.get("percent_complete", 0)
                                latest_str = f" | {m.get('latest_processed')}" if m.get('latest_processed') else ""
                                live_detail = f"\n     👉 Extraction: {c_ext + f_ext}/{t_ext} ({pct_ext}%){latest_str}"
                            elif m.get("latest_processed"):
                                live_detail = f"\n     👉 Active: {m.get('latest_processed')}"
                            elif m.get("total_screened") is not None and m.get("total_to_screen"):
                                live_detail = f"\n     👉 Progress: {m.get('total_screened')}/{m.get('total_to_screen')} screened ({m.get('passed', 0)} passed, {m.get('rejected', 0)} rejected)"

                        usd = pr_data.get("usd_cost")
                        tok = pr_data.get("tokens_consumed")
                        if usd or tok:
                            cost_detail = f" | Tokens: {tok or 0:,} (USD: ${float(usd or 0):.4f})"
                except Exception:
                    pass

            step_display = step_names.get(current_step, current_step)

            if current_step != last_step:
                logger.info(f"  👉 [STEP TRANSITION] [{step_display}] State: {current_status.upper()} | Time: {elapsed}s{cost_detail}{stats_summary}")
                if on_step_change:
                    on_step_change(proc)
                last_step = current_step
            else:
                logger.info(f"  ⏳ [IN PROGRESS: {step_display}] Elapsed: {elapsed}s{cost_detail}{stats_summary}{live_detail}")

            if current_status == "completed":
                logger.info(f"🎉 Agent Process '{process_id}' COMPLETED successfully in {elapsed}s!{cost_detail}")
                return proc
            elif current_status in ("failed", "aborted"):
                error_msg = proc.get("error_message") or proc.get("stop_reason")
                raise RuntimeError(
                    f"Agent Process '{process_id}' terminated with status '{current_status}' at step '{current_step}' after {elapsed}s: {error_msg}"
                )

            time.sleep(poll_interval_sec)

        raise TimeoutError(f"Agent Process '{process_id}' timed out after {max_timeout_sec}s. Last step: {last_step}")
