"""
Paper Comments & Collaboration Area End-to-End User Journey Scenario.

Validates the full collaborative workflow exclusively via the live HTTP REST API:
1. Fetching paper comments and verifying initial developer placeholder messages (/api/papers/{id}/comments/).
2. Verifying scorecard integration (/api/papers/{id}/scorecard/ has 'messages').
3. Creating a top-level researcher question comment via POST /api/papers/{id}/comments/.
4. Creating a threaded reply via POST /api/comments/ with parent_id.
5. Reacting with emojis (toggle on, toggle off, add rocket) via POST /api/comments/{id}/reactions/.
6. Editing a comment (PATCH /api/comments/{id}/) and asserting is_edited flag.
7. Verifying chronological chat ordering in paper comments and scorecard payload.
8. Resolving discussion threads via POST /api/comments/{id}/resolve/.
9. Security & validation guard (invalid reactions -> 400, fake UUID -> 404).
10. Soft-delete and hard-delete API cleanup restoring clean slate state.
"""

import logging
import random
import uuid
from typing import Dict, Any, Optional

from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    PipelineService,
    AgentService,
)

logger = logging.getLogger("e2e_paper_comments")


def run_paper_comments_collaboration_scenario(
    config: Optional[E2EConfig] = None,
    workspace_id: Optional[str] = None,
    paper_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the complete Paper Comments & Collaboration E2E User Journey via live HTTP REST API.
    """
    cfg = config or E2EConfig.from_env()
    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)

    ws_svc = WorkspaceService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("💬 STARTING PAPER COMMENTS & COLLABORATION E2E USER JOURNEY")
    logger.info(f"📍 Target API : {cfg.base_url}")
    logger.info("=================================================================")

    target_ws_id = workspace_id
    target_paper_id = paper_id
    created_temp_workspace = False

    # Step 0: Find or Provision Target Workspace & Paper
    if not target_paper_id and target_ws_id:
        papers = pipeline_svc.list_papers(workspace_id=target_ws_id, limit=5)
        if papers:
            target_paper_id = papers[0]["id"]

    if not target_paper_id:
        all_papers = pipeline_svc.list_papers(limit=5)
        if all_papers:
            target_paper_id = all_papers[0]["id"]
            target_ws_id = all_papers[0].get("workspace_id")

    if not target_paper_id:
        logger.info("📦 No papers found in accessible workspaces. Provisioning test workspace...")
        random_suffix = random.randint(100000, 999999)
        ws_data = ws_svc.create_workspace(
            name=f"test_e2e_comments_{random_suffix}",
            abstract_acceptance_criteria="Accept all relevant academic research papers.",
            abstract_rejection_criteria="Do not reject relevant papers.",
            full_text_acceptance_criteria="Accept papers with empirical evaluations.",
            full_text_rejection_criteria="Reject non-technical position papers.",
        )
        target_ws_id = ws_data["id"]
        created_temp_workspace = True

        ws_svc.create_scraper(
            workspace_id=target_ws_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"transformer architecture"',
            limit=1,
        )
        agent_svc = AgentService(client)
        logger.info("🚀 Ingesting 1 paper for comments collaboration validation...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=target_ws_id,
            name=f"Comments Provisioning - {target_ws_id}",
            limit=1,
            reprocess_existing=True,
        )
        agent_svc.poll_until_complete(
            agent_proc["id"], max_timeout_sec=cfg.max_timeout_sec
        )
        papers = pipeline_svc.list_papers(workspace_id=target_ws_id, limit=5)
        assert papers, "Provisioned workspace must contain at least one paper"
        target_paper_id = papers[0]["id"]

    logger.info(f"   • Selected Target Workspace ID : {target_ws_id}")
    logger.info(f"   • Selected Target Paper ID     : {target_paper_id}")

    results = {
        "status": "PASSED",
        "comments_count": 0,
        "tested_placeholder_messages": False,
        "tested_scorecard_messages": False,
        "tested_create_comment": False,
        "tested_threaded_reply": False,
        "tested_reactions": False,
        "tested_patch_edit": False,
        "tested_resolution": False,
        "tested_security_guard": False,
        "tested_soft_and_hard_delete": False,
    }

    c1_id = None
    c2_id = None

    try:
        # Phase 1: Verify Initial Placeholder Messages
        logger.info(f"📡 Phase 1: Checking initial placeholder messages on paper {target_paper_id}...")
        resp_init = client.get(f"/api/papers/{target_paper_id}/comments/", expected_status=200)
        init_comments = resp_init.json()
        assert isinstance(init_comments, list), "Comments endpoint must return a list"
        logger.info(f"   • Initial messages count: {len(init_comments)}")
        if init_comments and init_comments[0].get("id", "").startswith("00000000-0000"):
            logger.info("   • Default developer placeholder structure verified.")
        results["tested_placeholder_messages"] = True

        # Phase 1b: Verify Scorecard Endpoint Messages
        logger.info(f"📊 Phase 1b: Checking scorecard messages on paper {target_paper_id}...")
        resp_sc = client.get(f"/api/papers/{target_paper_id}/scorecard/", expected_status=200)
        sc_data = resp_sc.json()
        assert "messages" in sc_data, "Scorecard must have 'messages' at root"
        assert "paper" in sc_data and "messages" in sc_data["paper"], "Scorecard must have 'messages' inside paper object"
        logger.info("   • Scorecard messages integration verified.")
        results["tested_scorecard_messages"] = True

        # Phase 2: Create Top-Level Comment (Lead Question)
        logger.info("💬 Phase 2: Creating top-level research question comment via POST /api/papers/{id}/comments/...")
        q_payload = {
            "content": "Have we verified the attention scaling throughput on large benchmark datasets?",
            "comment_type": "question"
        }
        resp_c1 = client.post(
            f"/api/papers/{target_paper_id}/comments/",
            json_data=q_payload,
            expected_status=201
        )
        c1_data = resp_c1.json()
        c1_id = c1_data["id"]
        assert c1_data["content"] == q_payload["content"], "Created comment content must match payload"
        assert c1_data["status"] == "active", "Created comment must be active"
        assert c1_data["is_resolved"] is False, "Comment must not be resolved initially"
        logger.info(f"   • Created comment ID {c1_id} by {c1_data.get('user', {}).get('username')}")
        results["tested_create_comment"] = True

        # Phase 3: Create Threaded Reply via Dedicated ViewSet
        logger.info(f"🧵 Phase 3: Creating threaded reply to comment {c1_id} via POST /api/comments/...")
        reply_payload = {
            "paper": str(target_paper_id),
            "parent": str(c1_id),
            "content": "Rechecked table 4: throughput improves by **18.2%** with zero accuracy degradation.",
            "comment_type": "finding"
        }
        resp_c2 = client.post(
            "/api/comments/",
            json_data=reply_payload,
            expected_status=201
        )
        c2_data = resp_c2.json()
        c2_id = c2_data["id"]
        assert c2_data["parent_id"] == c1_id, "Reply parent_id must link to parent comment"
        logger.info(f"   • Created threaded reply ID {c2_id}")
        results["tested_threaded_reply"] = True

        # Phase 4: Emoji Reaction Lifecycle
        logger.info(f"👍 Phase 4: Testing reactions lifecycle on comment {c1_id}...")
        # A. Add bulb reaction
        resp_react_add = client.post(
            f"/api/comments/{c1_id}/reactions/",
            json_data={"reaction_type": "bulb"},
            expected_status=200
        )
        react_add_json = resp_react_add.json()
        assert react_add_json.get("action") == "added", "Action must be 'added'"
        bulb_entry = next((r for r in react_add_json.get("reactions", []) if r.get("reaction_type") == "bulb"), None)
        assert bulb_entry and bulb_entry.get("count", 0) >= 1, "Bulb reaction count must be at least 1"
        logger.info("   • Added 'bulb' reaction.")

        # B. Toggle bulb reaction off
        resp_react_toggle = client.post(
            f"/api/comments/{c1_id}/reactions/",
            json_data={"reaction_type": "bulb"},
            expected_status=200
        )
        assert resp_react_toggle.json().get("action") == "removed", "Toggling off must return 'removed'"
        logger.info("   • Toggled off 'bulb' reaction.")

        # C. Add rocket reaction
        resp_react_rocket = client.post(
            f"/api/comments/{c1_id}/reactions/",
            json_data={"reaction_type": "rocket"},
            expected_status=200
        )
        assert resp_react_rocket.json().get("action") == "added"
        logger.info("   • Added 'rocket' reaction.")
        results["tested_reactions"] = True

        # Phase 5: Edit Comment (PATCH)
        logger.info(f"✏️ Phase 5: Editing reply {c2_id} via PATCH /api/comments/{c2_id}/...")
        updated_content = "Rechecked table 4: throughput improves by **18.4%** across 5 random seeds."
        resp_edit = client.patch(
            f"/api/comments/{c2_id}/",
            json_data={"content": updated_content},
            expected_status=200
        )
        edit_data = resp_edit.json()
        assert edit_data["content"] == updated_content, "Content must be updated"
        assert edit_data["is_edited"] is True, "is_edited flag must be True after modification"
        logger.info("   • Successfully patched content and verified is_edited=True.")
        results["tested_patch_edit"] = True

        # Phase 6: Read Back and Verify Chronological Chat Ordering
        logger.info("📜 Phase 6: Reading back paper messages and verifying chat ordering...")
        resp_msgs = client.get(f"/api/papers/{target_paper_id}/comments/", expected_status=200)
        current_msgs = resp_msgs.json()
        assert len(current_msgs) >= 2, "Must return at least the 2 newly created comments"
        assert current_msgs[0]["id"] == c1_id, "Oldest message must appear on top (chat ordering)"
        assert current_msgs[1]["id"] == c2_id, "Newest reply must appear after parent"
        results["comments_count"] = len(current_msgs)
        logger.info(f"   • Chronological ordering verified ({len(current_msgs)} comments).")

        # Phase 7: Thread Resolution Lifecycle
        logger.info(f"✅ Phase 7: Resolving discussion thread on comment {c1_id}...")
        resp_resolve = client.post(
            f"/api/comments/{c1_id}/resolve/",
            json_data={"action": "resolve"},
            expected_status=200
        )
        resolve_data = resp_resolve.json()
        assert resolve_data["is_resolved"] is True, "is_resolved must be True"
        assert resolve_data["status"] == "resolved", "Status must be 'resolved'"
        logger.info("   • Discussion thread resolved successfully.")
        results["tested_resolution"] = True

        # Phase 8: Security & Validation Guard
        logger.info("🛡️ Phase 8: Testing security and validation guards...")
        # Invalid reaction type -> 400
        resp_bad_react = client.post(
            f"/api/comments/{c1_id}/reactions/",
            json_data={"reaction_type": "invalid_emoji_xyz"}
        )
        assert resp_bad_react.status_code == 400, f"Expected 400 for bad reaction, got {resp_bad_react.status_code}"

        # Unknown comment UUID -> 404
        fake_uuid = str(uuid.uuid4())
        resp_fake_comment = client.get(f"/api/comments/{fake_uuid}/")
        assert resp_fake_comment.status_code == 404, f"Expected 404 for unknown comment, got {resp_fake_comment.status_code}"
        logger.info("   • Security and validation guards verified.")
        results["tested_security_guard"] = True

        # Phase 9: Soft-Delete and Hard-Delete API Cleanup
        logger.info(f"🧹 Phase 9: Soft-deleting reply {c2_id} via DELETE /api/comments/{c2_id}/...")
        client.delete(f"/api/comments/{c2_id}/", expected_status=204)

        # Verify soft-deleted item hidden from standard active list
        resp_active = client.get(f"/api/comments/?paper={target_paper_id}", expected_status=200)
        active_items = resp_active.json() if isinstance(resp_active.json(), list) else resp_active.json().get("results", [])
        active_ids = [item["id"] for item in active_items]
        assert c2_id not in active_ids, "Soft-deleted comment must not appear in standard list"

        # Verify visible when include_deleted=true
        resp_with_del = client.get(f"/api/comments/?paper={target_paper_id}&include_deleted=true", expected_status=200)
        all_items = resp_with_del.json() if isinstance(resp_with_del.json(), list) else resp_with_del.json().get("results", [])
        assert any(item["id"] == c2_id for item in all_items), "Soft-deleted comment must appear with include_deleted=true"
        logger.info("   • Soft-delete lifecycle verified.")

        # Hard-delete both test comments to restore clean slate
        logger.info("🗑️ Permanent Hard-Delete of test comments...")
        client.delete(f"/api/comments/{c2_id}/?hard=true", expected_status=204)
        client.delete(f"/api/comments/{c1_id}/?hard=true", expected_status=204)

        # Verify clean slate return to placeholder messages
        resp_after = client.get(f"/api/papers/{target_paper_id}/comments/", expected_status=200)
        after_msgs = resp_after.json()
        assert after_msgs and after_msgs[0].get("id", "").startswith("00000000-0000"), "Comments must revert to developer placeholders after cleanup"
        logger.info("   • Permanent cleanup verified, clean slate restored.")
        results["tested_soft_and_hard_delete"] = True

    finally:
        if created_temp_workspace and target_ws_id and cfg.delete_after:
            try:
                ws_svc.delete_workspace(target_ws_id)
                logger.info(f"🧹 Cleaned up temporary workspace {target_ws_id}")
            except Exception as e:
                logger.warning(f"Could not delete temp workspace {target_ws_id}: {e}")

    assert results["tested_placeholder_messages"], "Placeholder messages test must pass"
    assert results["tested_scorecard_messages"], "Scorecard messages test must pass"
    assert results["tested_create_comment"], "Comment creation test must pass"
    assert results["tested_threaded_reply"], "Threaded reply test must pass"
    assert results["tested_reactions"], "Reactions test must pass"
    assert results["tested_patch_edit"], "Patch edit test must pass"
    assert results["tested_resolution"], "Resolution test must pass"
    assert results["tested_security_guard"], "Security guard test must pass"
    assert results["tested_soft_and_hard_delete"], "Soft and hard delete test must pass"

    logger.info("=================================================================")
    logger.info("🎉 PAPER COMMENTS & COLLABORATION E2E JOURNEY PASSED SUCCESSFULLY")
    logger.info("=================================================================")
    return results
