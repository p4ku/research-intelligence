import uuid
from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    Paper,
    PaperMetric,
    PipelineRun,
    ExtractionDefinition,
    Extraction,
    PaperComment,
    PaperCommentReaction,
)

User = get_user_model()


class PaperCommentModelTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="researcher_1", password="password123")
        self.user2 = User.objects.create_user(username="researcher_2", password="password123")
        self.user3 = User.objects.create_user(username="lead_scientist", password="password123")

        self.workspace_a = Workspace.objects.create(name="AI Lab A")
        self.workspace_b = Workspace.objects.create(name="Bio Lab B")

        self.paper_a1 = Paper.objects.create(
            workspace=self.workspace_a,
            hash_id="hash_a1_comment_test",
            title="Foundation Models in Drug Discovery",
            authors="Alice, Bob",
            abstract="A transformer-based molecular representation model.",
            source_database="arxiv"
        )
        self.paper_b1 = Paper.objects.create(
            workspace=self.workspace_b,
            hash_id="hash_b1_comment_test",
            title="CRISPR Screen Analysis",
            authors="Charlie",
            abstract="High-throughput genetic screening methods.",
            source_database="biorxiv"
        )

        self.run_a1 = PipelineRun.objects.create(
            workspace=self.workspace_a,
            name="Run Alpha 1"
        )
        self.run_b1 = PipelineRun.objects.create(
            workspace=self.workspace_b,
            name="Run Beta 1"
        )

    def test_global_paper_comment_creation_run_is_none(self):
        """When pipeline_run is None, the comment applies to the paper across all runs in the workspace."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            pipeline_run=None,
            user=self.user1,
            content="This is a foundational methodology paper applicable to all our screening pipelines.",
            comment_type=PaperComment.TYPE_GENERAL,
            status=PaperComment.STATUS_ACTIVE
        )
        self.assertIsNotNone(comment.id)
        self.assertIsNone(comment.pipeline_run)
        self.assertEqual(comment.workspace, self.workspace_a)
        self.assertEqual(comment.paper, self.paper_a1)
        self.assertIn("Global", str(comment))

    def test_run_specific_comment_creation(self):
        """When pipeline_run is provided, comment is tied to that specific run edition."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            pipeline_run=self.run_a1,
            user=self.user1,
            content="In Run Alpha 1, the signal score seems slightly suppressed due to missing patent claims.",
            comment_type=PaperComment.TYPE_FINDING
        )
        self.assertEqual(comment.pipeline_run, self.run_a1)
        self.assertIn("Run:", str(comment))

    def test_workspace_auto_inference(self):
        """If workspace is not explicitly passed, save() infers it from paper."""
        comment = PaperComment(
            paper=self.paper_a1,
            user=self.user1,
            content="Auto-inferring workspace from paper."
        )
        comment.save()
        self.assertEqual(comment.workspace_id, self.workspace_a.id)

    def test_cross_tenant_workspace_mismatch_raises_validation_error(self):
        """Comments cannot mix a paper from workspace A with workspace B."""
        comment = PaperComment(
            workspace=self.workspace_b,
            paper=self.paper_a1,
            user=self.user1,
            content="Invalid cross-workspace comment."
        )
        with self.assertRaises(ValidationError) as ctx:
            comment.clean()
        self.assertIn("workspace", ctx.exception.message_dict)

    def test_pipeline_run_workspace_mismatch_raises_validation_error(self):
        """PipelineRun must belong to the same workspace as the comment/paper."""
        comment = PaperComment(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            pipeline_run=self.run_b1,  # From workspace_b!
            user=self.user1,
            content="Invalid cross-workspace run assignment."
        )
        with self.assertRaises(ValidationError) as ctx:
            comment.clean()
        self.assertIn("pipeline_run", ctx.exception.message_dict)

    def test_threaded_replies_and_parent_integrity(self):
        """Replies must link to the same paper and workspace as the parent comment."""
        parent_comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user1,
            content="Can someone verify the batch size reported in section 3.2?",
            comment_type=PaperComment.TYPE_QUESTION
        )

        reply = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            parent=parent_comment,
            user=self.user2,
            content="Checked table 4: they used batch size 512 distributed across 8 H100s."
        )
        self.assertEqual(parent_comment.replies.count(), 1)
        self.assertEqual(parent_comment.replies.first(), reply)

        # Invalid reply pointing to different paper
        invalid_reply = PaperComment(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            parent=parent_comment,
            user=self.user2,
            content="Mismatch test"
        )
        invalid_reply.paper = self.paper_b1  # Deliberate mismatch
        with self.assertRaises(ValidationError) as ctx:
            invalid_reply.clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_researcher_mentions(self):
        """Researchers can be tagged / marked via ManyToMany relationship."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user1,
            content="Hey @researcher_2 and @lead_scientist, check out the novel loss function.",
            comment_type=PaperComment.TYPE_QUESTION
        )
        comment.mentions.add(self.user2, self.user3)

        self.assertEqual(comment.mentions.count(), 2)
        self.assertIn(self.user2, comment.mentions.all())
        self.assertIn(self.user3, comment.mentions.all())
        self.assertEqual(self.user2.paper_comment_mentions.first(), comment)

    def test_comment_types_and_status(self):
        """Comments support different types and lifecycle statuses."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user3,
            content="Highly relevant work with strong experimental validation on ChEMBL benchmark.",
            comment_type=PaperComment.TYPE_FINDING,
            status=PaperComment.STATUS_ACTIVE
        )
        self.assertEqual(comment.comment_type, PaperComment.TYPE_FINDING)
        self.assertEqual(comment.status, PaperComment.STATUS_ACTIVE)

    def test_anchoring_and_domain_extraction_link(self):
        """Comments can link to specific Domain Pool extractions and text anchors."""
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Model Architectures",
            system_prompt="Extract architecture",
            user_prompt_template="{paper_text}",
            response_schema={}
        )
        extraction = Extraction.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            extraction_definition=ext_def,
            category="ml_method",
            fields_data={"fields": {"architecture": "Transformer with Rotary Embeddings"}}
        )

        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            extraction=extraction,
            anchor_text="We employ rotary positional embeddings across all 48 attention heads.",
            anchor_context={"page": 4, "section": "Methodology", "paragraph": 2},
            user=self.user1,
            content="Matches our internal LLM pretraining setup perfectly.",
            comment_type=PaperComment.TYPE_EXTRACTION_NOTE
        )
        self.assertEqual(comment.extraction, extraction)
        self.assertIn("rotary positional embeddings", comment.anchor_text)
        self.assertEqual(comment.anchor_context.get("page"), 4)

        # Mismatched extraction from another paper
        mismatched_extraction = Extraction.objects.create(
            workspace=self.workspace_b,
            paper=self.paper_b1,
            category="assay",
            fields_data={}
        )
        invalid_comment = PaperComment(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            extraction=mismatched_extraction,
            user=self.user1,
            content="Invalid extraction link."
        )
        with self.assertRaises(ValidationError) as ctx:
            invalid_comment.clean()
        self.assertIn("extraction", ctx.exception.message_dict)

    def test_resolution_workflow_methods(self):
        """resolve() and unresolve() helper methods update status and timestamp."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user1,
            content="Is the source code open-sourced?",
            comment_type=PaperComment.TYPE_QUESTION
        )
        self.assertFalse(comment.is_resolved)
        self.assertEqual(comment.status, PaperComment.STATUS_ACTIVE)

        comment.resolve(resolving_user=self.user3)
        comment.refresh_from_db()
        self.assertTrue(comment.is_resolved)
        self.assertEqual(comment.status, PaperComment.STATUS_RESOLVED)
        self.assertEqual(comment.resolved_by, self.user3)
        self.assertIsNotNone(comment.resolved_at)

        comment.unresolve()
        comment.refresh_from_db()
        self.assertFalse(comment.is_resolved)
        self.assertEqual(comment.status, PaperComment.STATUS_ACTIVE)
        self.assertIsNone(comment.resolved_by)
        self.assertIsNone(comment.resolved_at)

    def test_soft_delete_lifecycle(self):
        """soft_delete() marks comment deleted while preserving row for thread hierarchy."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user1,
            content="Mistyped remark."
        )
        self.assertFalse(comment.is_deleted)
        comment.soft_delete()
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.status, PaperComment.STATUS_DELETED)
        self.assertIsNotNone(comment.deleted_at)

    def test_reactions_and_uniqueness(self):
        """Researchers can react to comments with unique reaction types per user."""
        comment = PaperComment.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a1,
            user=self.user1,
            content="Brilliant insight into scalability."
        )

        reaction = PaperCommentReaction.objects.create(
            comment=comment,
            user=self.user2,
            reaction_type=PaperCommentReaction.REACTION_BULB
        )
        self.assertIsNotNone(reaction.id)
        self.assertEqual(comment.reactions.count(), 1)
        self.assertIn("reacted bulb", str(reaction))

        # Duplicate reaction of the same type by the same user raises IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PaperCommentReaction.objects.create(
                comment=comment,
                user=self.user2,
                reaction_type=PaperCommentReaction.REACTION_BULB
            )

    def test_not_registered_in_admin_yet(self):
        """Verify model is NOT registered in Django admin as requested by the user."""
        self.assertNotIn(PaperComment, admin.site._registry)
        self.assertNotIn(PaperCommentReaction, admin.site._registry)


class PaperCommentsAPITestCase(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from research_intelligence.models import WorkspaceMember

        self.client = APIClient()
        self.user = User.objects.create_user(username="api_researcher", password="password123")
        self.client.force_authenticate(user=self.user)

        self.workspace = Workspace.objects.create(name="API Test Lab")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="researcher")

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="hash_api_comment_test",
            title="Transformer Scaling in BioNLP",
            authors="Alice, Bob",
            abstract="Study on large-scale models.",
            source_database="arxiv"
        )
        self.run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run API 1"
        )
        self.metric = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run,
            signal_score=88.5,
            screening_status="accepted"
        )

    def test_paper_comments_api_returns_placeholder_messages_when_empty(self):
        """GET /api/papers/{id}/comments/ returns placeholder messages when no comments exist."""
        resp = self.client.get(f"/api/papers/{self.paper.id}/comments/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first_msg = data[0]
        self.assertIn("content", first_msg)
        self.assertIn("user", first_msg)
        self.assertIn("status", first_msg)
        self.assertIn("comment_type", first_msg)
        self.assertIn("created_at", first_msg)

    def test_paper_scorecard_api_returns_messages(self):
        """GET /api/papers/{id}/scorecard/?pipeline_run=... returns messages in both top-level and paper."""
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("messages", data)
        self.assertIn("paper", data)
        self.assertIn("messages", data["paper"])

    def test_dedicated_comments_endpoint_get_and_post(self):
        """GET and POST /api/papers/{id}/comments/ manages collaborative messages."""
        # Initial GET returns placeholder
        resp_get = self.client.get(f"/api/papers/{self.paper.id}/comments/?pipeline_run={self.run.id}")
        self.assertEqual(resp_get.status_code, 200)
        self.assertGreater(len(resp_get.json()), 0)

        # POST creates a real comment
        payload = {
            "content": "Can we reproduce results in section 4?",
            "comment_type": "question",
            "pipeline_run": str(self.run.id)
        }
        resp_post = self.client.post(f"/api/papers/{self.paper.id}/comments/", payload, format="json")
        self.assertEqual(resp_post.status_code, 201)
        created = resp_post.json()
        self.assertEqual(created["content"], payload["content"])
        self.assertEqual(created["user"]["username"], self.user.username)

        # Subsequent GET returns real comments, oldest first
        resp_get2 = self.client.get(f"/api/papers/{self.paper.id}/comments/?pipeline_run={self.run.id}")
        self.assertEqual(resp_get2.status_code, 200)
        data = resp_get2.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["content"], payload["content"])

    def test_permissions_and_crud_workflow_via_viewset(self):
        """
        Verify:
        - Workspace member creates a comment
        - Author (owner) can edit comment
        - Other regular researcher CANNOT edit comment (403)
        - Workspace admin CAN edit and delete comment
        - Workspace manager CAN edit and delete comment
        - Other regular researcher CANNOT delete comment (403)
        - User from another workspace CANNOT read or create (404/403, zero data leakage)
        """
        from research_intelligence.models import WorkspaceMember

        # Setup users in workspace
        other_researcher = User.objects.create_user(username="other_researcher", password="password123")
        WorkspaceMember.objects.create(workspace=self.workspace, user=other_researcher, role="researcher")

        ws_admin = User.objects.create_user(username="ws_admin", password="password123")
        WorkspaceMember.objects.create(workspace=self.workspace, user=ws_admin, role="admin")

        ws_manager = User.objects.create_user(username="ws_manager", password="password123")
        WorkspaceMember.objects.create(workspace=self.workspace, user=ws_manager, role="manager")

        # Setup external user in separate workspace
        external_workspace = Workspace.objects.create(name="External Lab")
        external_user = User.objects.create_user(username="external_researcher", password="password123")
        WorkspaceMember.objects.create(workspace=external_workspace, user=external_user, role="researcher")

        # 1. Author creates comment via /api/comments/
        self.client.force_authenticate(user=self.user)
        create_payload = {
            "paper": str(self.paper.id),
            "content": "Original analysis by primary researcher.",
            "comment_type": "finding",
        }
        res_create = self.client.post("/api/comments/", create_payload, format="json")
        self.assertEqual(res_create.status_code, 201)
        comment_id = res_create.json()["id"]

        # 2. Author edits their own comment -> 200 OK
        edit_payload = {"content": "Author revised analysis."}
        res_edit_owner = self.client.patch(f"/api/comments/{comment_id}/", edit_payload, format="json")
        self.assertEqual(res_edit_owner.status_code, 200)
        self.assertEqual(res_edit_owner.json()["content"], "Author revised analysis.")
        self.assertTrue(res_edit_owner.json()["is_edited"])

        # 3. Other regular researcher attempts to edit -> 403 Forbidden
        self.client.force_authenticate(user=other_researcher)
        res_edit_other = self.client.patch(f"/api/comments/{comment_id}/", {"content": "Unauthorized edit."}, format="json")
        self.assertEqual(res_edit_other.status_code, 403)

        # 4. Other regular researcher attempts to delete -> 403 Forbidden
        res_del_other = self.client.delete(f"/api/comments/{comment_id}/")
        self.assertEqual(res_del_other.status_code, 403)

        # 5. Workspace manager edits comment -> 200 OK
        self.client.force_authenticate(user=ws_manager)
        res_edit_mgr = self.client.patch(f"/api/comments/{comment_id}/", {"content": "Manager note added."}, format="json")
        self.assertEqual(res_edit_mgr.status_code, 200)
        self.assertEqual(res_edit_mgr.json()["content"], "Manager note added.")

        # 6. Workspace admin edits comment -> 200 OK
        self.client.force_authenticate(user=ws_admin)
        res_edit_admin = self.client.patch(f"/api/comments/{comment_id}/", {"content": "Admin approved finding."}, format="json")
        self.assertEqual(res_edit_admin.status_code, 200)

        # 7. External user attempts to retrieve comment -> 404 Not Found (Zero data leakage!)
        self.client.force_authenticate(user=external_user)
        res_ext_get = self.client.get(f"/api/comments/{comment_id}/")
        self.assertEqual(res_ext_get.status_code, 404)

        # 8. External user attempts to create comment on paper -> 403 Forbidden
        res_ext_post = self.client.post("/api/comments/", create_payload, format="json")
        self.assertEqual(res_ext_post.status_code, 403)

        # 9. Workspace member resolves and unresolves comment
        self.client.force_authenticate(user=self.user)
        res_resolve = self.client.post(f"/api/comments/{comment_id}/resolve/")
        self.assertEqual(res_resolve.status_code, 200)
        self.assertTrue(res_resolve.json()["is_resolved"])

        res_unresolve = self.client.post(f"/api/comments/{comment_id}/resolve/", {"action": "unresolve"})
        self.assertEqual(res_unresolve.status_code, 200)
        self.assertFalse(res_unresolve.json()["is_resolved"])

        # 10. Workspace member reacts with emoji
        res_react = self.client.post(f"/api/comments/{comment_id}/reactions/", {"reaction_type": "rocket"})
        self.assertEqual(res_react.status_code, 200)
        self.assertEqual(res_react.json()["action"], "added")
        self.assertEqual(len(res_react.json()["reactions"]), 1)

        # Toggle reaction off
        res_react_toggle = self.client.post(f"/api/comments/{comment_id}/reactions/", {"reaction_type": "rocket"})
        self.assertEqual(res_react_toggle.status_code, 200)
        self.assertEqual(res_react_toggle.json()["action"], "removed")

        # 11. Soft delete by author
        res_delete_soft = self.client.delete(f"/api/comments/{comment_id}/")
        self.assertEqual(res_delete_soft.status_code, 204)
        # Should be filtered out from standard list
        res_list = self.client.get(f"/api/comments/?paper={self.paper.id}")
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json() if isinstance(res_list.json(), list) else res_list.json().get("results", [])
        self.assertEqual(len(items), 0)
        # But visible with ?include_deleted=true
        res_list_deleted = self.client.get(f"/api/comments/?paper={self.paper.id}&include_deleted=true")
        self.assertEqual(res_list_deleted.status_code, 200)
        del_items = res_list_deleted.json() if isinstance(res_list_deleted.json(), list) else res_list_deleted.json().get("results", [])
        self.assertEqual(len(del_items), 1)

        # 12. Hard delete by admin
        self.client.force_authenticate(user=ws_admin)
        res_delete_hard = self.client.delete(f"/api/comments/{comment_id}/?hard=true")
        self.assertEqual(res_delete_hard.status_code, 204)
        self.assertFalse(PaperComment.objects.filter(id=comment_id).exists())


