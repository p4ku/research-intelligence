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

    def is_enabled(self) -> bool:
        """Checks if the workflow scheduling feature is enabled on the target server."""
        try:
            resp = self.client.get("/api/schedules/")
            if resp.status_code == 404:
                body = resp.text.lower()
                if "disabled" in body or "scheduling" in body:
                    return False
            return resp.status_code == 200
        except Exception:
            return False

    def create_schedule(
        self,
        workspace_id: str,
        name: str,
        frequency: str = "daily",
        time_of_day: str = "02:00:00",
        timezone_name: str = "UTC",
        cron_expression: Optional[str] = None,
        one_off_datetime: Optional[str] = None,
        prevent_overlap: bool = True,
        max_consecutive_failures: int = 3,
        reprocess_existing: bool = True,
        configuration_override: Optional[Dict[str, Any]] = None,
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
            "configuration_override": configuration_override or {},
            "is_active": is_active,
        }
        if one_off_datetime:
            payload["one_off_datetime"] = one_off_datetime
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

    def toggle_schedule(self, schedule_id: str) -> Dict[str, Any]:
        logger.info(f"🔄 Toggling Workflow Schedule '{schedule_id}' active state...")
        resp = self.client.post(f"/api/schedules/{schedule_id}/toggle/", expected_status=200)
        data = resp.json()
        logger.info(f"✅ Workflow Schedule '{schedule_id}' active state is now: {data.get('is_active')}")
        return data

    def deactivate_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Ensures schedule is deactivated (is_active=False) so it never fires automatically."""
        try:
            sched = self.get_schedule(schedule_id)
            if sched.get("is_active"):
                return self.toggle_schedule(schedule_id)
            return sched
        except Exception as e:
            logger.debug(f"Could not deactivate schedule '{schedule_id}': {e}")
            return None

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

    def cleanup_old_test_schedules(self, prefix: str = "Test Schedule", workspace_prefix: str = "test_e2e_") -> int:
        """Finds and deletes/deactivates any previous test schedules to prevent accidental Celery Beat runs."""
        logger.info("🧹 Checking for lingering test workflow schedules to purge/deactivate...")
        try:
            scheds = self.list_schedules()
            count = 0
            for s in scheds:
                s_name = s.get("name", "")
                ws_name = s.get("workspace_name", "")
                s_id = s.get("id")
                is_test = prefix in s_name or ws_name.startswith(workspace_prefix) or "Daily Test Schedule" in s_name or "One-Off Test Schedule" in s_name
                if is_test and s_id:
                    logger.info(f"   🗑️ Purging lingering test schedule '{s_name}' ({s_id})...")
                    try:
                        self.delete_schedule(s_id)
                        count += 1
                    except Exception:
                        self.deactivate_schedule(s_id)
                        count += 1
            if count > 0:
                logger.info(f"✅ Purged/deactivated {count} lingering test schedule(s).")
            else:
                logger.info("✅ No lingering test schedules found.")
            return count
        except Exception as e:
            logger.warning(f"Note on schedule cleanup: {e}")
            return 0
