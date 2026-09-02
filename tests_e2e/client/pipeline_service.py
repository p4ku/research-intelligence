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

    def list_papers(self, workspace_id: str = None, screening_status: str = None, pipeline_run: str = None) -> List[Dict[str, Any]]:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        if screening_status:
            params["screening_status"] = screening_status
        if pipeline_run:
            params["pipeline_run"] = pipeline_run
        resp = self.client.get("/api/papers/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def list_extractions(self, workspace_id: str) -> List[Dict[str, Any]]:
        params = {"workspace": workspace_id}
        resp = self.client.get("/api/extractions/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def list_reports(self, workspace_id: str) -> List[Dict[str, Any]]:
        params = {"workspace": workspace_id}
        resp = self.client.get("/api/reports/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data
