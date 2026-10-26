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

    @staticmethod
    def get_default_e2e_extraction_definitions(prefix: str = "test_e2e_") -> List[Dict[str, Any]]:
        """
        Returns standard extraction target definitions for E2E scenarios.
        """
        return [
            {
                "name": f"{prefix}fit_score",
                "exit_metrics": ["fit_score"],
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": "Evaluate strategic fit for enterprise research from 0.0 to 100.0.",
                "user_prompt_template": "Paper Title: {title}\nAbstract/Content:\n{content}\nEvaluate strategic fit (0-100).",
                "response_schema": {
                    "type": "object",
                    "required": ["fit_score", "justification"],
                    "properties": {
                        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "justification": {"type": "string"},
                    }
                },
                "is_active": True,
            },
            {
                "name": f"{prefix}novelty_score",
                "exit_metrics": ["novelty_score"],
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": "Evaluate scientific novelty and originality from 0.0 to 100.0.",
                "user_prompt_template": "Paper Title: {title}\nAbstract/Content:\n{content}\nEvaluate novelty score (0-100).",
                "response_schema": {
                    "type": "object",
                    "required": ["novelty_score", "justification"],
                    "properties": {
                        "novelty_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "justification": {"type": "string"},
                    }
                },
                "is_active": True,
            },
            {
                "name": f"{prefix}trl_level",
                "exit_metrics": ["trl_level"],
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": "Evaluate Technology Readiness Level from 1 to 9.",
                "user_prompt_template": "Paper Title: {title}\nAbstract/Content:\n{content}\nEvaluate TRL level (1-9).",
                "response_schema": {
                    "type": "object",
                    "required": ["trl_level", "justification"],
                    "properties": {
                        "trl_level": {"type": "integer", "minimum": 1, "maximum": 9},
                        "justification": {"type": "string"},
                    }
                },
                "is_active": True,
            },
        ]

    def create_workspace(
        self,
        name: str,
        abstract_acceptance_criteria: str = "Accept all relevant academic research papers.",
        abstract_rejection_criteria: str = "Do not reject relevant papers.",
        full_text_acceptance_criteria: str = "Accept papers with empirical evaluations.",
        full_text_rejection_criteria: str = "Reject non-technical position papers.",
        abstract_screening_system_prompt: Optional[str] = None,
        abstract_screening_user_prompt_template: Optional[str] = None,
        abstract_screening_response_schema: Optional[Dict[str, Any]] = None,
        abstract_screening_exit_metric: Optional[str] = None,
        full_text_screening_system_prompt: Optional[str] = None,
        full_text_screening_user_prompt_template: Optional[str] = None,
        full_text_screening_response_schema: Optional[Dict[str, Any]] = None,
        full_text_screening_exit_metric: Optional[str] = None,
        narrative_report_system_prompt: Optional[str] = None,
        narrative_report_prompt: Optional[str] = None,
        narrative_report_top_n_papers: Optional[int] = 10,
        signal_score_code: Optional[str] = None,
        screening_llm_model: str = "google/gemini-3.8-flash",
        llm_provider: str = "google",
        ocr_provider: Optional[str] = None,
        reasoning_effort: str = "medium",
        skip_abstract_screening: bool = False,
        reprocess_existing: bool = True,
        monthly_token_limit: Optional[int] = None,
        monthly_usd_limit: Optional[float] = None,
        extraction_definitions: Optional[List[Dict[str, Any]]] = None,
        scrapers: Optional[List[Dict[str, Any]]] = None,
        subscribers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "name": name,
            "abstract_acceptance_criteria": abstract_acceptance_criteria,
            "abstract_rejection_criteria": abstract_rejection_criteria,
            "abstract_screening_system_prompt": abstract_screening_system_prompt,
            "abstract_screening_user_prompt_template": abstract_screening_user_prompt_template,
            "abstract_screening_response_schema": abstract_screening_response_schema,
            "abstract_screening_exit_metric": abstract_screening_exit_metric,
            "full_text_acceptance_criteria": full_text_acceptance_criteria,
            "full_text_rejection_criteria": full_text_rejection_criteria,
            "full_text_screening_system_prompt": full_text_screening_system_prompt,
            "full_text_screening_user_prompt_template": full_text_screening_user_prompt_template,
            "full_text_screening_response_schema": full_text_screening_response_schema,
            "full_text_screening_exit_metric": full_text_screening_exit_metric,
            "narrative_report_system_prompt": narrative_report_system_prompt,
            "narrative_report_prompt": narrative_report_prompt,
            "narrative_report_top_n_papers": narrative_report_top_n_papers,
            "signal_score_code": signal_score_code,
            "screening_llm_model": screening_llm_model,
            "llm_provider": llm_provider,
            "ocr_provider": ocr_provider,
            "reasoning_effort": reasoning_effort,
            "skip_abstract_screening": skip_abstract_screening,
            "reprocess_existing": reprocess_existing,
        }
        if monthly_token_limit is not None:
            payload["monthly_token_limit"] = monthly_token_limit
        if monthly_usd_limit is not None:
            payload["monthly_usd_limit"] = monthly_usd_limit
        if extraction_definitions is None:
            extraction_definitions = self.get_default_e2e_extraction_definitions(prefix=f"{name}_")
        if extraction_definitions:
            payload["extraction_definitions"] = extraction_definitions
        if scrapers:
            payload["scrapers"] = scrapers
        if subscribers:
            payload["subscribers"] = subscribers

        logger.info(f"🏗️ Creating Workspace '{name}' with full dual-stage criteria, dynamic schemas & extraction targets...")
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

    def add_member(self, workspace_id: str, username: str, role: str = "researcher") -> Dict[str, Any]:
        """Adds a user as member to workspace with role ('admin', 'manager', 'researcher')."""
        resp = self.client.post(
            f"/api/workspaces/{workspace_id}/members/",
            json_data={"username": username, "role": role},
            expected_status=201,
        )
        data = resp.json()
        logger.info(f"   👥 Added member '{username}' (role: {role}) to workspace {workspace_id}.")
        return data

    def list_members(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Lists all members of a workspace."""
        resp = self.client.get(f"/api/workspaces/{workspace_id}/members/", expected_status=200)
        data = resp.json()
        return data if isinstance(data, list) else data.get("results", [])

    def remove_member(self, workspace_id: str, username: str) -> bool:
        """Removes a user from workspace memberships."""
        logger.info(f"   👥 Removing member '{username}' from workspace {workspace_id}...")
        resp = self.client.delete(f"/api/workspaces/{workspace_id}/members/?username={username}")
        if resp.status_code in (200, 204):
            logger.info(f"   ✅ Member '{username}' removed from workspace {workspace_id}.")
            return True
        elif resp.status_code == 405:
            logger.debug(f"ℹ️ DELETE /api/workspaces/{workspace_id}/members/ not implemented on server (405).")
            return False
        else:
            logger.warning(f"⚠️ Could not remove member '{username}': {resp.status_code} - {resp.text}")
            return False

    def cleanup_test_members(self, workspace_id: str, usernames: List[str]) -> int:
        """Removes a list of test members from the specified workspace."""
        removed = 0
        for u in usernames:
            try:
                if self.remove_member(workspace_id, u):
                    removed += 1
            except Exception as e:
                logger.debug(f"Failed to remove member '{u}' from workspace {workspace_id}: {e}")
        return removed

    def cleanup_old_test_workspaces(self, prefix: str = "test_e2e_") -> int:
        """
        Finds and deletes all previous test workspaces matching prefix (e.g. 'test_e2e_').
        """
        logger.info(f"🧹 Checking for previous '{prefix}*' test workspaces to clean up...")
        try:
            workspaces = self.list_workspaces()
            to_delete = [ws for ws in workspaces if ws.get("name", "").startswith(prefix)]
            count = 0
            for ws in to_delete:
                ws_id = ws.get("id")
                ws_name = ws.get("name")
                logger.info(f"   🗑️ Purging previous test workspace '{ws_name}' ({ws_id})...")
                self.delete_workspace(ws_id)
                count += 1
            if count > 0:
                logger.info(f"✅ Cleaned up {count} old test workspace(s).")
            else:
                logger.info("✅ No previous test workspaces found.")
            return count
        except Exception as e:
            logger.warning(f"Could not complete pre-cleanup of old test workspaces: {e}")
            return 0

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
        exit_metrics: list[str] | str,
        postprocessing_code: Optional[str] = None,
        llm_model: str = "google/gemini-3.8-flash",
        primary_frontend_metric: Optional[str] = None,
        secondary_frontend_metrics: Optional[str] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        metrics_list = (
            [m.strip() for m in exit_metrics.split(',') if m.strip()]
            if isinstance(exit_metrics, str)
            else (list(exit_metrics) if exit_metrics else [])
        )
        payload = {
            "workspace": workspace_id,
            "name": name,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "response_schema": response_schema,
            "exit_metrics": metrics_list,
            "llm_model": llm_model,
            "is_active": True,
            **kwargs,
        }
        if primary_frontend_metric is not None:
            payload["primary_frontend_metric"] = primary_frontend_metric
        if secondary_frontend_metrics is not None:
            payload["secondary_frontend_metrics"] = (
                [m.strip() for m in secondary_frontend_metrics.split(',') if m.strip()]
                if isinstance(secondary_frontend_metrics, str)
                else list(secondary_frontend_metrics)
            )
        if postprocessing_code is not None:
            payload["postprocessing_code"] = postprocessing_code

        logger.info(f"📊 Defining Extraction Target '{name}' (exit_metrics: '{metrics_list}', postprocessing: {bool(postprocessing_code)})...")
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

    def update_extraction_definition(
        self,
        definition_id: str,
        exit_metrics: Optional[list[str] | str] = None,
        postprocessing_code: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        payload = dict(kwargs)
        if exit_metrics is not None:
            payload["exit_metrics"] = (
                [m.strip() for m in exit_metrics.split(',') if m.strip()]
                if isinstance(exit_metrics, str)
                else list(exit_metrics)
            )
        if postprocessing_code is not None:
            payload["postprocessing_code"] = postprocessing_code

        resp = self.client.patch(f"/api/extraction-definitions/{definition_id}/", json_data=payload)
        assert resp.status_code == 200, f"Failed to update extraction definition: {resp.status_code} - {resp.text}"
        return resp.json()

    def list_extraction_definitions(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        resp = self.client.get("/api/extraction-definitions/", params=params)
        if resp.status_code == 404:
            return []
        data = resp.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        if workspace_id and isinstance(results, list):
            results = [d for d in results if str(d.get("workspace")) == str(workspace_id)]
        return results

    def delete_extraction_definition(self, definition_id: str) -> bool:
        resp = self.client.delete(f"/api/extraction-definitions/{definition_id}/")
        return resp.status_code in (200, 204)

    def cleanup_old_extraction_definitions(self, prefix: str = "test_e2e_") -> int:
        """
        Finds and deletes all previous extraction definitions matching prefix (e.g. 'test_e2e_').
        """
        logger.info(f"🧹 Checking for previous '{prefix}*' extraction definitions to clean up...")
        try:
            defs = self.list_extraction_definitions()
            to_delete = [d for d in defs if d.get("name", "").startswith(prefix)]
            count = 0
            for d in to_delete:
                def_id = d.get("id")
                def_name = d.get("name")
                logger.info(f"   🗑️ Purging previous extraction definition '{def_name}' ({def_id})...")
                if self.delete_extraction_definition(def_id):
                    count += 1
            if count > 0:
                logger.info(f"✅ Cleaned up {count} old extraction definition(s).")
            else:
                logger.info("✅ No previous extraction definitions found.")
            return count
        except Exception as e:
            logger.warning(f"Could not complete pre-cleanup of old extraction definitions: {e}")
            return 0

    def update_workspace(self, workspace_id: str, **kwargs) -> Dict[str, Any]:
        """Update workspace fields via PATCH."""
        resp = self.client.patch(f"/api/workspaces/{workspace_id}/", json_data=kwargs, expected_status=200)
        return resp.json()

    def export_configuration(self, workspace_id: str) -> Dict[str, Any]:
        """Export complete workspace configuration as a portable JSON template bundle."""
        logger.info(f"📦 Exporting configuration bundle for workspace '{workspace_id}'...")
        resp = self.client.get(f"/api/workspaces/{workspace_id}/export-configuration/", expected_status=200)
        data = resp.json()
        logger.info(f"✅ Exported configuration bundle successfully (version: {data.get('version')}).")
        return data

    def import_configuration(
        self,
        bundle: Any,
        update_existing: bool = True,
    ) -> Dict[str, Any]:
        """Import workspace configuration bundle (creates or updates workspaces and components)."""
        logger.info(f"📥 Importing workspace configuration bundle (update_existing={update_existing})...")
        payload = bundle if isinstance(bundle, (dict, list)) else {"workspaces": [bundle]}
        if isinstance(payload, dict):
            payload["overwrite_existing"] = update_existing
            payload["update_existing"] = update_existing
        resp = self.client.post("/api/workspaces/import-configuration/", json_data=payload, expected_status=200)
        data = resp.json()
        stats = data.get("stats", {})
        logger.info(
            f"✅ Import completed: "
            f"{stats.get('created_workspaces', 0)} ws created, {stats.get('updated_workspaces', 0)} ws updated | "
            f"{stats.get('created_extractions', 0)} ext created | "
            f"{stats.get('created_scrapers', 0)} scrapers created | "
            f"{stats.get('created_subscribers', 0)} subscribers created"
        )
        return data

    def is_subscribers_enabled(self) -> bool:
        """Checks if the email notifications / subscribers feature is enabled on the target server."""
        try:
            resp = self.client.get("/api/subscribers/")
            if resp.status_code == 404:
                body = resp.text.lower()
                if "disabled" in body or "subscribers" in body or "email" in body:
                    return False
            return resp.status_code == 200
        except Exception:
            return False

    def create_subscriber(
        self,
        workspace_id: str,
        email: str,
        name: str = "",
        subscription_type: str = "result_report",
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """Create a subscriber for workspace notifications."""
        payload = {
            "workspace": workspace_id,
            "email": email,
            "name": name,
            "subscription_type": subscription_type,
            "is_active": is_active,
        }
        logger.info(f"📧 Adding subscriber '{email}' [{subscription_type}] to workspace '{workspace_id}'...")
        resp = self.client.post("/api/subscribers/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ Subscriber registered with ID: {data.get('id')}")
        return data

    def list_subscribers(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List subscribers, optionally scoped by workspace."""
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        resp = self.client.get("/api/subscribers/", params=params, expected_status=200)
        data = resp.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        if workspace_id and isinstance(results, list):
            results = [s for s in results if str(s.get("workspace")) == str(workspace_id)]
        return results

    def delete_subscriber(self, subscriber_id: str) -> bool:
        """Delete subscriber by ID."""
        resp = self.client.delete(f"/api/subscribers/{subscriber_id}/")
        return resp.status_code in (200, 204)

    def list_editions(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List editions for a workspace."""
        resp = self.client.get(f"/api/workspaces/{workspace_id}/editions/", expected_status=200)
        data = resp.json()
        return data if isinstance(data, list) else data.get("results", [])

    def get_edition_detail(
        self,
        workspace_id: str,
        date: str,
        run_id: Optional[str] = None,
        scope: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        min_score: Optional[float] = None,
        sort: Optional[str] = None,
        dimension_filters: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Fetch edition detail with optional run, scope, pagination, min_score, sort, and dynamic dimension filtering."""
        params = {}
        if run_id:
            params["run_id"] = run_id
        if scope:
            params["scope"] = scope
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if min_score is not None:
            params["min_score"] = min_score
        if sort:
            params["sort"] = sort
        if dimension_filters:
            for dim_k, dim_v in dimension_filters.items():
                if dim_v is not None:
                    if dim_k.startswith(('min_', 'dim:', 'dim_min:', 'min_dim:')):
                        params[dim_k] = dim_v
                    else:
                        params[f"min_{dim_k}"] = dim_v
        if kwargs:
            params.update(kwargs)

        resp = self.client.get(f"/api/workspaces/{workspace_id}/editions/{date}/", params=params, expected_status=200)
        return resp.json()


