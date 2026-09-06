"""
Pipeline, Papers, and Extractions Query Service for E2E Tests.
"""

import logging
from typing import Dict, Any, List
from .api_client import APIClient

logger = logging.getLogger("e2e_pipeline")


class PipelineService:
    def __init__(self, client: APIClient):
        self.client = client

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
