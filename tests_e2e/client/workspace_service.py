"""
Workspace, Scrapers, and Extraction Definitions Service for E2E Tests.
"""

import logging
from typing import Dict, Any, List, Optional
from .api_client import APIClient

logger = logging.getLogger("e2e_workspace")


class WorkspaceService:
    def __init__(self, client: APIClient):
        self.client = client

    def create_workspace(
        self,
        name: str,
        abstract_acceptance_criteria: str,
        abstract_rejection_criteria: str,
        full_text_acceptance_criteria: str,
        full_text_rejection_criteria: str,
        signal_score_code: Optional[str] = None,
        screening_llm_model: str = "google/gemini-3.7-flash",
        ocr_provider: Optional[str] = None,
        reasoning_effort: str = "medium",
        skip_abstract_screening: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "name": name,
            "abstract_acceptance_criteria": abstract_acceptance_criteria,
            "abstract_rejection_criteria": abstract_rejection_criteria,
            "full_text_acceptance_criteria": full_text_acceptance_criteria,
            "full_text_rejection_criteria": full_text_rejection_criteria,
            "signal_score_code": signal_score_code,
            "screening_llm_model": screening_llm_model,
            "ocr_provider": ocr_provider,
            "reasoning_effort": reasoning_effort,
            "skip_abstract_screening": skip_abstract_screening,
        }
        logger.info(f"🏗️ Creating Workspace '{name}'...")
        resp = self.client.post("/api/workspaces/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ Workspace created with ID: {data.get('id')}")
        return data

    def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/workspaces/{workspace_id}/", expected_status=200)
        return resp.json()

    def list_workspaces(self) -> List[Dict[str, Any]]:
        resp = self.client.get("/api/workspaces/", expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def delete_workspace(self, workspace_id: str) -> None:
        logger.info(f"🗑️ Deleting Workspace '{workspace_id}'...")
        self.client.delete(f"/api/workspaces/{workspace_id}/", expected_status=204)
        logger.info(f"✅ Workspace '{workspace_id}' deleted.")

    def create_scraper(
        self,
        workspace_id: str,
        provider: str,
        search_query: str,
        limit: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        payload = {
            "workspace": workspace_id,
            "provider": provider,
            "search_query": search_query,
            "limit": limit,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "is_active": True,
        }
        logger.info(f"🔍 Configuring Scraper for '{provider}' (query: '{search_query}', limit: {limit})...")
        resp = self.client.post("/api/scrapers/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ Scraper created with ID: {data.get('id')}")
        return data

    def create_extraction_definition(
        self,
        workspace_id: str,
        name: str,
        system_prompt: str,
        user_prompt_template: str,
        response_schema: Dict[str, Any],
        exit_metric: str,
        llm_model: str = "google/gemini-3.7-flash",
    ) -> Optional[Dict[str, Any]]:
        payload = {
            "workspace": workspace_id,
            "name": name,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "response_schema": response_schema,
            "exit_metric": exit_metric,
            "llm_model": llm_model,
            "is_active": True,
        }
        logger.info(f"📊 Defining Extraction Target '{name}' (exit_metric: '{exit_metric}')...")
        resp = self.client.post("/api/extraction-definitions/", json_data=payload)
        if resp.status_code == 201:
            data = resp.json()
            logger.info(f"✅ Extraction Definition created with ID: {data.get('id')}")
            return data
        elif resp.status_code == 404:
            logger.warning(f"⚠️ /api/extraction-definitions/ not available on this server version (HTTP 404). Proceeding.")
            return None
        else:
            raise AssertionError(f"Failed to create extraction definition: {resp.status_code} - {resp.text}")
