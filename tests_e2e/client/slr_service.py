"""
Systematic Literature Review (SLR) REST API Service for E2E Tests.
Wraps all /api/slr/ endpoints for audit queue, screening votes,
parameter extraction audit, dispute adjudication, PRISMA flow, and RoB.
"""

from typing import Any, Dict, List, Optional
from .api_client import APIClient


class SLRService:
    def __init__(self, client: APIClient):
        self.client = client

    def get_workspace_config(self, workspace_id: str) -> Dict[str, Any]:
        """GET /api/slr/workspaces/{workspace_id}/config/"""
        resp = self.client.get(f"/api/slr/workspaces/{workspace_id}/config/", expected_status=200)
        return resp.json()

    def update_workspace_config(self, workspace_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/slr/workspaces/{workspace_id}/config/"""
        resp = self.client.put(f"/api/slr/workspaces/{workspace_id}/config/", json_data=config_data, expected_status=200)
        return resp.json()

    def get_my_queue(self) -> List[Dict[str, Any]]:
        """GET /api/slr/cohorts/my-queue/"""
        resp = self.client.get("/api/slr/cohorts/my-queue/", expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def get_cohort(self, cohort_id: str) -> Dict[str, Any]:
        """GET /api/slr/cohorts/{cohort_id}/"""
        resp = self.client.get(f"/api/slr/cohorts/{cohort_id}/", expected_status=200)
        return resp.json()

    def get_cohort_paper(self, cohort_id: str, paper_id: str) -> Dict[str, Any]:
        """GET /api/slr/cohorts/{cohort_id}/papers/{paper_id}/"""
        resp = self.client.get(f"/api/slr/cohorts/{cohort_id}/papers/{paper_id}/", expected_status=200)
        return resp.json()

    def submit_screening_review(
        self,
        cohort_id: str,
        paper_id: str,
        action: str = "agree",
        exclusion_reason: Optional[str] = None,
        reviewer_note: Optional[str] = None,
        evidence_citation: Optional[str] = None,
        time_spent_seconds: int = 15,
    ) -> Dict[str, Any]:
        """POST /api/slr/cohorts/{cohort_id}/papers/{paper_id}/review/"""
        payload = {
            "action": action,
            "exclusion_reason": exclusion_reason,
            "reviewer_note": reviewer_note,
            "evidence_citation": evidence_citation,
            "time_spent_seconds": time_spent_seconds,
        }
        resp = self.client.post(f"/api/slr/cohorts/{cohort_id}/papers/{paper_id}/review/", json_data=payload, expected_status=200)
        return resp.json()

    def submit_extraction_audit(
        self,
        cohort_id: str,
        extraction_id: str,
        action: str = "verify",
        corrected_fields: Optional[Dict[str, Any]] = None,
        verified_evidence_quotes: Optional[List[Dict[str, Any]]] = None,
        reviewer_notes: Optional[str] = None,
        time_spent_seconds: int = 10,
    ) -> Dict[str, Any]:
        """POST /api/slr/cohorts/{cohort_id}/extractions/{extraction_id}/audit/"""
        payload = {
            "action": action,
            "corrected_fields": corrected_fields,
            "verified_evidence_quotes": verified_evidence_quotes or [],
            "reviewer_notes": reviewer_notes,
            "time_spent_seconds": time_spent_seconds,
        }
        resp = self.client.post(f"/api/slr/cohorts/{cohort_id}/extractions/{extraction_id}/audit/", json_data=payload, expected_status=200)
        return resp.json()

    def resume_pipeline_run(self, run_id: str) -> Dict[str, Any]:
        """POST /api/slr/runs/{run_id}/resume/"""
        resp = self.client.post(f"/api/slr/runs/{run_id}/resume/", expected_status=200)
        return resp.json()

    def get_prisma_metrics(self, run_id: str) -> Dict[str, Any]:
        """GET /api/slr/runs/{run_id}/prisma/"""
        resp = self.client.get(f"/api/slr/runs/{run_id}/prisma/", expected_status=200)
        return resp.json()

    def get_rob_assessments(self, run_id: str) -> List[Dict[str, Any]]:
        """GET /api/slr/runs/{run_id}/rob/"""
        resp = self.client.get(f"/api/slr/runs/{run_id}/rob/", expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def list_disputes(self) -> List[Dict[str, Any]]:
        """GET /api/slr/disputes/"""
        resp = self.client.get("/api/slr/disputes/", expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def resolve_dispute(
        self,
        dispute_id: str,
        final_decision: str = "include",
        resolution_rationale: str = "Resolved by Senior Arbiter",
        final_exclusion_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /api/slr/disputes/{dispute_id}/resolve/"""
        payload = {
            "final_decision": final_decision,
            "resolution_rationale": resolution_rationale,
            "final_exclusion_reason": final_exclusion_reason,
        }
        resp = self.client.post(f"/api/slr/disputes/{dispute_id}/resolve/", json_data=payload, expected_status=200)
        return resp.json()
