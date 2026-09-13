"""
Run Admission Guard E2E Scenario.
The only test that exercises the Workspace row lock behind admit_run() on a
real Postgres (unit tests run on SQLite where select_for_update is a no-op):
1. Fires six starts with six distinct windows at once -> exactly five 201 and one 409 `run_limit_reached`.
2. Fires two starts with the same window at once -> exactly one 201 and one 409 `duplicate_run`.
3. Aborts every run, then one more start is admitted (the slots are released).
Runs are started with limit=1 and aborted right after the assertions to keep cost low.
"""

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from ..config import E2EConfig
from ..client import APIClient, AuthService, WorkspaceService, AgentService

logger = logging.getLogger("e2e_run_admission")

MAX_IN_FLIGHT = 5


def _start(client: APIClient, workspace_id: str, window: Dict[str, Any], name: str) -> Tuple[int, Dict[str, Any]]:
    payload = {"workspace_id": workspace_id, "name": name, "limit": 1, "autonomous": True, **window}
    resp = client.post("/api/pipeline-runs/start/", json_data=payload)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return resp.status_code, body


def _fire(client: APIClient, workspace_id: str, windows: List[Dict[str, Any]], label: str) -> List[Tuple[int, Dict[str, Any]]]:
    with ThreadPoolExecutor(max_workers=len(windows)) as pool:
        futures = [
            pool.submit(_start, client, workspace_id, window, f"{label} {idx}")
            for idx, window in enumerate(windows, start=1)
        ]
        return [f.result() for f in futures]


def _abort_all(agent_svc: AgentService, results: List[Tuple[int, Dict[str, Any]]]) -> None:
    for status_code, body in results:
        if status_code == 201 and body.get("pipeline_run_id"):
            try:
                agent_svc.abort_agent(body["pipeline_run_id"])
            except Exception as err:
                logger.warning(f"Could not abort run {body.get('pipeline_run_id')}: {err}")


def run_run_admission_guard_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    cfg = config or E2EConfig.from_env()
    suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_run_admission_{suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)

    logger.info("=================================================================")
    logger.info("🚦 STARTING RUN ADMISSION GUARD SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning papers.",
        abstract_rejection_criteria="Reject everything unrelated to computing.",
        full_text_acceptance_criteria="Accept empirical evaluations.",
        full_text_rejection_criteria="Reject opinion pieces.",
        signal_score_code="score = 0.5 * fit_score + 0.5 * 9.0\nreturn round(score * 10.0, 2)",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"transformer"',
            limit=1,
        )

        # 1. Six distinct windows at once: five admitted, one refused for capacity.
        windows = [{"n_last_days": days} for days in (3, 5, 7, 10, 14, 21)]
        logger.info(f"🚀 Firing {len(windows)} concurrent starts (cap is {MAX_IN_FLIGHT})...")
        burst = _fire(client, workspace_id, windows, "Burst")
        codes = sorted(code for code, _ in burst)
        refused = [body for code, body in burst if code == 409]
        logger.info(f"📊 Status codes: {codes}")
        assert codes.count(201) == MAX_IN_FLIGHT, f"Expected {MAX_IN_FLIGHT} admitted starts, got {codes}"
        assert codes.count(409) == 1, f"Expected exactly one 409, got {codes}"
        assert refused[0].get("code") == "run_limit_reached", f"Unexpected refusal body: {refused[0]}"
        assert refused[0].get("in_flight") == MAX_IN_FLIGHT and refused[0].get("limit") == MAX_IN_FLIGHT, refused[0]

        # A seventh start, sequential, is refused too (the cap holds once reached).
        code, body = _start(client, workspace_id, {"n_last_days": 30}, "Seventh")
        assert code == 409 and body.get("code") == "run_limit_reached", (code, body)

        _abort_all(agent_svc, burst)
        _wait_until_no_in_flight(client, workspace_id, cfg.max_timeout_sec)

        # 2. Two identical windows at once: one admitted, one refused as a duplicate.
        same = {"start_date": "2026-08-01", "end_date": "2026-08-15"}
        logger.info("🚀 Firing 2 concurrent starts with the same window...")
        pair = _fire(client, workspace_id, [same, dict(same)], "Twin")
        pair_codes = sorted(code for code, _ in pair)
        assert pair_codes == [201, 409], f"Expected [201, 409], got {pair_codes}: {[b for _, b in pair]}"
        dup = next(body for code, body in pair if code == 409)
        assert dup.get("code") == "duplicate_run", dup
        admitted = next(body for code, body in pair if code == 201)
        assert dup.get("conflicting_run_id") == admitted.get("pipeline_run_id"), (dup, admitted)

        # A different window in the same workspace is still admitted alongside it.
        code, body = _start(client, workspace_id, {"start_date": "2026-08-01", "end_date": "2026-08-16"}, "Neighbour")
        assert code == 201, (code, body)

        _abort_all(agent_svc, pair + [(code, body)])
        _wait_until_no_in_flight(client, workspace_id, cfg.max_timeout_sec)

        # 3. Slots released: a fresh start is admitted.
        code, body = _start(client, workspace_id, {"n_last_days": 7}, "After abort")
        assert code == 201, (code, body)
        _abort_all(agent_svc, [(code, body)])

        logger.info("=================================================================")
        logger.info("🎉 RUN ADMISSION GUARD SCENARIO PASSED!")
        logger.info("=================================================================")
        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "burst_status_codes": codes,
            "duplicate_status_codes": pair_codes,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not clean up test workspace: {del_err}")


def _wait_until_no_in_flight(client: APIClient, workspace_id: str, timeout_sec: int) -> None:
    """Abort is honoured at the next tick; wait for the workspace to have no run in flight."""
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        resp = client.get("/api/pipeline-runs/", params={"workspace": workspace_id, "page_size": 50}, expected_status=200)
        payload = resp.json()
        runs = payload.get("results", payload) if isinstance(payload, dict) else payload
        in_flight = [r for r in runs if r.get("status") in ("pending", "running", "paused")]
        if not in_flight:
            return
        time.sleep(2.0)
    raise AssertionError(f"Runs still in flight after {timeout_sec}s in workspace {workspace_id}")
