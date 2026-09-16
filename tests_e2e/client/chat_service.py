"""
Chat & Knowledge Explorer Service for E2E Tests.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from .api_client import APIClient

logger = logging.getLogger("e2e_chat")


class ChatService:
    def __init__(self, client: APIClient):
        self.client = client

    def ask_paper_sync(
        self,
        workspace_id: str,
        question: str,
        paper_id: Optional[str] = None,
        session_id: Optional[str] = None,
        deep_thinking: bool = False,
        timeout_sec: int = 240,
    ) -> Dict[str, Any]:
        payload = {
            "workspace_id": workspace_id,
            "question": question,
            "paper_id": paper_id,
            "session_id": session_id,
            "deep_thinking": deep_thinking,
        }
        logger.info(f"💬 Asking Paper Chat (Q: '{question[:60]}...')...")
        resp = self.client.post("/api/chat/", json_data=payload)
        
        if resp.status_code not in (200, 202):
            raise AssertionError(f"Unexpected chat status {resp.status_code}: {resp.text}")

        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "completed":
            logger.info(f"✅ Received synchronous answer from Chat Engine (Session ID: {data.get('session_id')})")
            return data

        message_id = data.get("message_id")
        if not message_id:
            return data

        logger.info(f"⏳ Polling chat message '{message_id}' on Celery worker...")
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            msg_resp = self.client.get(f"/api/chat/messages/{message_id}/", expected_status=200)
            msg_data = msg_resp.json()
            st = msg_data.get("status")
            if st == "completed":
                logger.info(f"✅ Chat message '{message_id}' completed in {int(time.time() - t0)}s!")
                return msg_data
            elif st == "failed":
                raise RuntimeError(f"Chat message '{message_id}' failed: {msg_data.get('error_message')}")
            time.sleep(2.0)

        raise TimeoutError(f"Chat message '{message_id}' timed out after {timeout_sec}s.")

    def list_sessions(
        self,
        workspace_id: Optional[str] = None,
        paper_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params = {}
        if workspace_id:
            params["workspace_id"] = workspace_id
        if paper_id:
            params["paper_id"] = paper_id
        resp = self.client.get("/api/chat/sessions/", params=params, expected_status=200)
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def get_session(self, session_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/api/chat/sessions/{session_id}/", expected_status=200)
        return resp.json()

    def delete_session(self, session_id: str) -> bool:
        resp = self.client.delete(f"/api/chat/sessions/{session_id}/")
        return resp.status_code in (200, 204)


