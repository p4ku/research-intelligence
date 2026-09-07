"""
Pipeline, Papers, and Extractions Query Service for E2E Tests.
"""

import logging
from typing import Dict, Any, List, Optional
from .api_client import APIClient

logger = logging.getLogger("e2e_pipeline")


class PipelineService:
    def __init__(self, client: APIClient):
        self.client = client

    def start_pipeline_run(
        self,
        workspace_id: str,
        name: str = "Autonomous Pipeline Run",
        limit: int = 10,
        skip_abstract_screening: bool = False,
        reprocess_existing: bool = True,
        autonomous: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Starts an autonomous pipeline run via /api/pipeline-runs/start/ or /api/agents/.
        """
        payload = {
            "workspace_id": workspace_id,
            "name": name,
            "limit": limit,
            "skip_abstract_screening": skip_abstract_screening,
            "reprocess_existing": reprocess_existing,
            "autonomous": autonomous,
            **kwargs,
        }
        resp = self.client.post("/api/pipeline-runs/start/", json_data=payload, expected_status=201)
        data = resp.json()
        data["pipeline_run_id"] = data.get("pipeline_run_id") or data.get("id")
        return data

    def poll_pipeline_run_to_completion(
        self,
        pipeline_run_id: str,
        timeout_seconds: int = 900,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Polls a pipeline run until it reaches a terminal status ('completed', 'failed', 'aborted').
        """
        import time
        t0 = time.time()
        while time.time() - t0 < timeout_seconds:
            data = self.get_pipeline_run(pipeline_run_id)
            status = data.get("status")
            if status in ("completed", "failed", "aborted"):
                return data
            time.sleep(poll_interval)
        raise TimeoutError(f"Pipeline run {pipeline_run_id} timed out after {timeout_seconds}s")

    def get_pipeline_run(self, pipeline_run_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/pipeline-runs/{pipeline_run_id}/", expected_status=200)
        return resp.json()

    def get_component_runs(self, pipeline_run_id: str) -> List[Dict[str, Any]]:
        resp = self.client.get(f"/api/component-runs/?pipeline_run={pipeline_run_id}", expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def list_pipeline_runs(
        self,
        workspace_id: str = None,
        status: str = None,
        page: int = None,
        page_size: int = None,
        return_full_response: bool = False,
    ) -> Any:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if status:
            params["status"] = status
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        resp = self.client.get("/api/pipeline-runs/", params=params, expected_status=200)
        data = resp.json()
        if return_full_response:
            return data
        return data.get("results", data) if isinstance(data, dict) else data

    def list_papers(
        self,
        workspace_id: str = None,
        screening_status: str = None,
        pipeline_run: str = None,
        search: str = None,
        page: int = None,
        page_size: int = None,
        return_full_response: bool = False,
    ) -> Any:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if screening_status:
            params["screening_status"] = screening_status
        if pipeline_run:
            params["pipeline_run"] = pipeline_run
        if search:
            params["search"] = search
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        resp = self.client.get("/api/papers/", params=params, expected_status=200)
        data = resp.json()
        if return_full_response:
            return data
        return data.get("results", data) if isinstance(data, dict) else data

    def get_paper(self, paper_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/papers/{paper_id}/", expected_status=200)
        return resp.json()

    def get_paper_scorecard(self, paper_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/papers/{paper_id}/scorecard/", expected_status=200)
        return resp.json()

    def get_paper_pdf_status(self, paper_id: str) -> int:
        resp = self.client.get(f"/api/papers/{paper_id}/pdf/")
        return resp.status_code

    def list_paper_metrics(
        self,
        workspace_id: str = None,
        pipeline_run: str = None,
        paper_id: str = None,
        screening_status: str = None,
        page: int = None,
        page_size: int = None,
        return_full_response: bool = False,
    ) -> Any:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if pipeline_run:
            params["pipeline_run"] = pipeline_run
        if paper_id:
            params["paper"] = paper_id
        if screening_status:
            params["screening_status"] = screening_status
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        resp = self.client.get("/api/paper-metrics/", params=params, expected_status=200)
        data = resp.json()
        if return_full_response:
            return data
        return data.get("results", data) if isinstance(data, dict) else data

    def list_extractions(
        self,
        workspace_id: str = None,
        paper_id: str = None,
        definition_id: str = None,
        pipeline_run_id: str = None,
        page: int = None,
        page_size: int = None,
        return_full_response: bool = False,
    ) -> Any:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if paper_id:
            params["paper"] = paper_id
        if definition_id:
            params["definition"] = definition_id
        if pipeline_run_id:
            params["pipeline_run"] = pipeline_run_id
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        resp = self.client.get("/api/extractions/", params=params, expected_status=200)
        data = resp.json()
        if return_full_response:
            return data
        return data.get("results", data) if isinstance(data, dict) else data

    def list_reports(
        self,
        workspace_id: str,
        page: int = None,
        page_size: int = None,
        return_full_response: bool = False,
    ) -> Any:
        params = {"workspace": workspace_id}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        resp = self.client.get("/api/reports/", params=params, expected_status=200)
        data = resp.json()
        if return_full_response:
            return data
        return data.get("results", data) if isinstance(data, dict) else data

    def get_extraction(self, extraction_id: str) -> Dict[str, Any]:
        """Fetch single extraction record by ID."""
        resp = self.client.get(f"/api/extractions/{extraction_id}/", expected_status=200)
        return resp.json()

    def create_hitl_correction(
        self,
        extraction_id: str,
        action: str,
        original_value: Any,
        corrected_value: Any = None,
        reason: str = "",
        human_operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit Human-in-the-Loop (HITL) analyst override."""
        payload = {
            "extraction": extraction_id,
            "action": action,
            "original_value": original_value,
            "corrected_value": corrected_value,
            "reason": reason,
            "human_operator": human_operator or "lead_analyst@example.com",
        }
        logger.info(f"👨‍🔬 Submitting HITL override '{action}' on extraction '{extraction_id}'...")
        resp = self.client.post("/api/hitl/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ HITL override recorded with ID: {data.get('id')}")
        return data

    def list_hitl_corrections(
        self,
        workspace_id: str = None,
        extraction_id: str = None,
    ) -> List[Dict[str, Any]]:
        """List HITL corrections, optionally filtered by workspace or extraction."""
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if extraction_id:
            params["extraction"] = extraction_id
        resp = self.client.get("/api/hitl/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def get_hitl_correction(self, correction_id: str) -> Dict[str, Any]:
        """Get HITL correction record by ID."""
        resp = self.client.get(f"/api/hitl/{correction_id}/", expected_status=200)
        return resp.json()

    def delete_hitl_correction(self, correction_id: str) -> bool:
        """Delete HITL correction record by ID."""
        resp = self.client.delete(f"/api/hitl/{correction_id}/")
        return resp.status_code in (200, 204)

