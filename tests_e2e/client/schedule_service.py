"""
Workflow Schedule Service for E2E Tests.
"""

import logging
from typing import Dict, Any, List, Optional
from .api_client import APIClient

logger = logging.getLogger("e2e_schedule")


class ScheduleService:
    def __init__(self, client: APIClient):
        self.client = client

    def create_schedule(
        self,
        workspace_id: str,
        name: str,
        frequency: str = "daily",
        time_of_day: str = "02:00:00",
        timezone_name: str = "UTC",
        cron_expression: Optional[str] = None,
        prevent_overlap: bool = True,
        max_consecutive_failures: int = 3,
        reprocess_existing: bool = False,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "workspace": workspace_id,
            "name": name,
            "frequency": frequency,
            "time_of_day": time_of_day,
            "timezone_name": timezone_name,
            "cron_expression": cron_expression or "",
            "prevent_overlap": prevent_overlap,
            "max_consecutive_failures": max_consecutive_failures,
            "reprocess_existing": reprocess_existing,
            "is_active": is_active,
        }
        logger.info(f"📅 Creating Workflow Schedule '{name}' for workspace '{workspace_id}' (freq: {frequency})...")
        resp = self.client.post("/api/schedules/", json_data=payload, expected_status=201)
        data = resp.json()
        logger.info(f"✅ Workflow Schedule created! Schedule ID: {data.get('id')}")
        return data

    def get_schedule(self, schedule_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/schedules/{schedule_id}/", expected_status=200)
        return resp.json()

    def list_schedules(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if workspace_id:
            params["workspace"] = workspace_id
        resp = self.client.get("/api/schedules/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def trigger_schedule(self, schedule_id: str, force: bool = False) -> Dict[str, Any]:
        logger.info(f"🚀 Triggering Workflow Schedule '{schedule_id}' (force={force})...")
        resp = self.client.post(f"/api/schedules/{schedule_id}/trigger/", json_data={"force": force}, expected_status=200)
        data = resp.json()
        logger.info(f"✅ Workflow Schedule triggered! Response: {data}")
        return data

    def delete_schedule(self, schedule_id: str) -> None:
        logger.info(f"🗑️ Deleting Workflow Schedule '{schedule_id}'...")
        self.client.delete(f"/api/schedules/{schedule_id}/", expected_status=204)
        logger.info(f"✅ Workflow Schedule '{schedule_id}' deleted.")
