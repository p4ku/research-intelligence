from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
    UserActivityLog,
    ExtractionDefinition,
    Extraction,
    HITLCorrection,
    NarrativeReport,
)
from chat.models import PaperChatSession, PaperChatMessage
from api.middleware import redact_sensitive_payload


class APISecurityFixesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin_sec",
            email="admin_sec@example.com",
            password="AdminPassword123!"
        )
        self.researcher_user = User.objects.create_user(
            username="researcher_sec",
            email="researcher_sec@example.com",
            password="ResearcherPassword123!"
        )
        self.manager_user = User.objects.create_user(
            username="manager_sec",
            email="manager_sec@example.com",
            password="ManagerPassword123!"
        )
        self.other_user = User.objects.create_user(
            username="other_sec",
            email="other_sec@example.com",
            password="OtherPassword123!"
        )

        self.workspace = Workspace.objects.create(name="Security Test Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.manager_user, role="manager")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.researcher_user, role="researcher")

    def test_middleware_sensitive_data_redaction(self):
        """Verify password, token, and API key redaction in dicts/lists."""
        payload = {
            "username": "alice",
            "password": "MyPlaintextPassword!",
            "nested": {
                "access": "secret_jwt_access_token",
                "refresh_token": "secret_refresh_token",
                "safe_field": "visible_value",
            },
            "items_list": ["item1", {"api_key": "raw_secret_key"}]
        }
        redacted = redact_sensitive_payload(payload)
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["access"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["refresh_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["safe_field"], "visible_value")
        self.assertEqual(redacted["items_list"][1]["api_key"], "[REDACTED]")

    def test_workspace_rbac_researcher_cannot_update_workspace(self):
        """Researcher cannot update workspace settings (requires admin/manager)."""
        self.client.force_authenticate(user=self.researcher_user)
        res = self.client.patch(f"/api/workspaces/{self.workspace.id}/", {
            "name": "Hacked Workspace Name"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can update workspace settings
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.patch(f"/api/workspaces/{self.workspace.id}/", {
            "name": "Updated Workspace Name"
        }, format="json")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_chat_session_owner_isolation_and_rename(self):
        """User cannot see, modify, or delete another user's session without admin role."""
        session_res = PaperChatSession.objects.create(
            workspace=self.workspace,
            user=self.researcher_user,
            title="Researcher Private Chat"
        )
        session_other = PaperChatSession.objects.create(
            workspace=self.workspace,
            user=self.other_user,
            title="Other Private Chat"
        )

        # Researcher cannot see Other's session
        self.client.force_authenticate(user=self.researcher_user)
        list_res = self.client.get("/api/chat/sessions/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        session_ids = [s["id"] for s in list_res.data]
        self.assertIn(str(session_res.id), session_ids)
        self.assertNotIn(str(session_other.id), session_ids)

        # Researcher can rename own session
        patch_res = self.client.patch(f"/api/chat/sessions/{session_res.id}/", {
            "title": "Renamed Chat Title"
        }, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        session_res.refresh_from_db()
        self.assertEqual(session_res.title, "Renamed Chat Title")

        # Researcher cannot delete other's session
        del_res = self.client.delete(f"/api/chat/sessions/{session_other.id}/")
        self.assertIn(del_res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_logout_and_token_blacklist(self):
        """Test that logging out blacklists the refresh token."""
        refresh = RefreshToken.for_user(self.admin_user)
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.post("/api/auth/logout/", {
            "refresh": str(refresh)
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Reusing the blacklisted token should fail
        refresh_attempt = self.client.post("/api/auth/refresh/", {
            "refresh": str(refresh)
        }, format="json")
        self.assertEqual(refresh_attempt.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_enforces_validation(self):
        """Verify that password change enforces validation rules."""
        self.client.force_authenticate(user=self.researcher_user)
        # Attempt simple short password
        res = self.client.post("/api/auth/change-password/", {
            "old_password": "ResearcherPassword123!",
            "new_password": "123",
            "confirm_password": "123"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_custom_exception_handler_consistent_envelope(self):
        """Verify standard error structure on 404 and 400."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get("/api/workspaces/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("status_code", res.data)
        self.assertIn("error", res.data)
        self.assertEqual(res.data["status_code"], 404)

    def test_reports_and_audit_logs_are_strictly_read_only(self):
        """Verify that reports and activity logs reject POST/PUT/PATCH/DELETE with 405."""
        self.client.force_authenticate(user=self.admin_user)

        # Reports endpoint
        res_report_post = self.client.post("/api/reports/", {"title": "Fake Report"}, format="json")
        self.assertEqual(res_report_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Activity logs endpoint
        res_log_post = self.client.post("/api/activity-logs/", {"action_name": "Fake Action"}, format="json")
        self.assertEqual(res_log_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_pipeline_runs_and_agents_disallow_arbitrary_put_patch(self):
        """Verify that PipelineRun and Agent processes reject arbitrary PUT/PATCH with 405."""
        self.client.force_authenticate(user=self.admin_user)
        run = PipelineRun.objects.create(workspace=self.workspace, status="pending")
        res_run_put = self.client.put(f"/api/pipeline-runs/{run.id}/", {"status": "completed"}, format="json")
        self.assertEqual(res_run_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_run_patch = self.client.patch(f"/api/pipeline-runs/{run.id}/", {"status": "completed"}, format="json")
        self.assertEqual(res_run_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_pagination_on_papers_endpoint(self):
        """Verify standard Django DRF PageNumberPagination on /api/papers/."""
        self.client.force_authenticate(user=self.admin_user)
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        # Create 12 dummy papers
        for i in range(12):
            Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=run,
                title=f"Paginated Paper #{i+1}",
                hash_id=f"hash_pag_{i}"
            )

        # Page 1 with page_size=5
        res_p1 = self.client.get(f"/api/papers/?workspace={self.workspace.id}&page=1&page_size=5")
        self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
        self.assertIn("count", res_p1.data)
        self.assertIn("results", res_p1.data)
        self.assertIn("next", res_p1.data)
        self.assertEqual(res_p1.data["count"], 12)
        self.assertEqual(len(res_p1.data["results"]), 5)
        self.assertIsNotNone(res_p1.data["next"])
        self.assertIsNone(res_p1.data["previous"])

        # Page 2 with page_size=5
        res_p2 = self.client.get(f"/api/papers/?workspace={self.workspace.id}&page=2&page_size=5")
        self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_p2.data["results"]), 5)
        self.assertIsNotNone(res_p2.data["previous"])

        # Page 3 with page_size=5 (remaining 2)
        res_p3 = self.client.get(f"/api/papers/?workspace={self.workspace.id}&page=3&page_size=5")
        self.assertEqual(res_p3.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_p3.data["results"]), 2)
        self.assertIsNone(res_p3.data["next"])

    def test_pagination_on_reports_and_extractions(self):
        """Verify pagination on /api/reports/ and /api/extractions/."""
        self.client.force_authenticate(user=self.admin_user)
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        # Create dummy reports
        for i in range(6):
            NarrativeReport.objects.create(
                workspace=self.workspace,
                pipeline_run=run,
                title=f"Report #{i+1}",
                content_markdown="# Summary"
            )

        res_rep = self.client.get(f"/api/reports/?workspace={self.workspace.id}&page=1&page_size=2")
        self.assertEqual(res_rep.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rep.data["count"], 6)
        self.assertEqual(len(res_rep.data["results"]), 2)

        # Create dummy extractions
        paper = Paper.objects.create(workspace=self.workspace, pipeline_run=run, title="Extraction Paper", hash_id="ext_paper_hash")
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Test Metric",
            system_prompt="Prompt",
            user_prompt_template="Template",
            response_schema={"type": "object"}
        )
        for i in range(4):
            Extraction.objects.create(
                workspace=self.workspace,
                paper=paper,
                extraction_definition=ext_def,
                category="test_metric",
                fields_data={"score": i}
            )

        res_ext = self.client.get(f"/api/extractions/?workspace={self.workspace.id}&page=1&page_size=2")
        self.assertEqual(res_ext.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ext.data["count"], 4)
        self.assertEqual(len(res_ext.data["results"]), 2)

    def test_ordering_on_endpoints(self):
        """Verify Django REST framework OrderingFilter on endpoints."""
        self.client.force_authenticate(user=self.admin_user)
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")

        p_alpha = Paper.objects.create(workspace=self.workspace, pipeline_run=run, title="Alpha Paper", hash_id="h_alpha")
        p_zeta = Paper.objects.create(workspace=self.workspace, pipeline_run=run, title="Zeta Paper", hash_id="h_zeta")
        p_beta = Paper.objects.create(workspace=self.workspace, pipeline_run=run, title="Beta Paper", hash_id="h_beta")

        PaperMetric.objects.create(workspace=self.workspace, pipeline_run=run, paper=p_alpha, signal_score=10.0)
        PaperMetric.objects.create(workspace=self.workspace, pipeline_run=run, paper=p_zeta, signal_score=90.0)
        PaperMetric.objects.create(workspace=self.workspace, pipeline_run=run, paper=p_beta, signal_score=50.0)

        # Ascending title ordering
        res_asc = self.client.get(f"/api/papers/?workspace={self.workspace.id}&ordering=title")
        self.assertEqual(res_asc.status_code, status.HTTP_200_OK)
        titles_asc = [p["title"] for p in res_asc.data]
        self.assertEqual(titles_asc, ["Alpha Paper", "Beta Paper", "Zeta Paper"])

        # Descending signal_score ordering
        res_score_desc = self.client.get(f"/api/papers/?workspace={self.workspace.id}&ordering=-signal_score")
        self.assertEqual(res_score_desc.status_code, status.HTTP_200_OK)
        titles_score = [p["title"] for p in res_score_desc.data]
        self.assertEqual(titles_score, ["Zeta Paper", "Beta Paper", "Alpha Paper"])

    def test_chat_message_owner_isolation(self):
        """Verify that researcher cannot fetch message details from another researcher's session."""
        session_other = PaperChatSession.objects.create(
            workspace=self.workspace,
            user=self.other_user,
            title="Other Secret Chat"
        )
        msg_other = PaperChatMessage.objects.create(
            session=session_other,
            sender="assistant",
            message="Confidential answer",
            status="completed"
        )

        self.client.force_authenticate(user=self.researcher_user)
        res = self.client.get(f"/api/chat/messages/{msg_other.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can view
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get(f"/api/chat/messages/{msg_other.id}/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_workspace_mass_assignment_protection(self):
        """Verify that client cannot overwrite token consumption or spend metrics via API."""
        self.client.force_authenticate(user=self.admin_user)
        self.workspace.tokens_consumed_this_month = 50000
        self.workspace.usd_spent_this_month = 12.50
        self.workspace.save()

        # Try to zero out billing counters via PATCH
        res = self.client.patch(f"/api/workspaces/{self.workspace.id}/", {
            "tokens_consumed_this_month": 0,
            "usd_spent_this_month": 0.00
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.tokens_consumed_this_month, 50000)
        self.assertEqual(float(self.workspace.usd_spent_this_month), 12.50)

    def test_ssrf_url_guard(self):
        """Verify that private IPs, loopback, and metadata endpoints are blocked."""
        from research_intelligence.utils.url_guard import is_safe_external_url, safe_download_url, SafeRedirectHandler
        self.assertFalse(is_safe_external_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_external_url("http://127.0.0.1:8000/api/"))
        self.assertFalse(is_safe_external_url("http://localhost:6379/"))
        self.assertFalse(is_safe_external_url("http://10.0.0.1/admin/"))
        self.assertFalse(is_safe_external_url("http://192.168.1.1/secret"))
        self.assertFalse(is_safe_external_url("file:///etc/passwd"))
        self.assertFalse(is_safe_external_url("gopher://127.0.0.1:6379"))
        self.assertTrue(is_safe_external_url("https://arxiv.org/pdf/2401.00001.pdf"))

        # Verify safe_download_url rejects unsafe initial URL immediately
        with self.assertRaises(ValueError) as ctx:
            safe_download_url("http://169.254.169.254/latest/meta-data/")
        self.assertIn("disallowed", str(ctx.exception).lower())

        # Verify SafeRedirectHandler blocks redirects to private IP endpoints
        handler = SafeRedirectHandler(max_redirects=3)
        with self.assertRaises(ValueError) as red_ctx:
            handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1:8000/internal")
        self.assertIn("disallowed internal or private ip", str(red_ctx.exception).lower())

        # Verify SafeRedirectHandler enforces max redirect limit
        handler._redirects = 3
        with self.assertRaises(ValueError) as limit_ctx:
            handler.redirect_request(None, None, 302, "Found", {}, "https://arxiv.org/pdf/2")
        self.assertIn("exceeded maximum redirect limit", str(limit_ctx.exception).lower())

    def test_indirect_prompt_injection_guard(self):
        """Verify that workspace screening templates encapsulate untrusted text in tags and directives."""
        sys_prompt = self.workspace.get_abstract_screening_system_prompt()
        user_prompt = self.workspace.get_abstract_screening_user_prompt_template()

        self.assertIn("INDIRECT PROMPT INJECTION GUARD", sys_prompt)
        self.assertIn("<UNTRUSTED_DOCUMENT_CONTENT>", user_prompt)
        self.assertIn("</UNTRUSTED_DOCUMENT_CONTENT>", user_prompt)

        ft_sys_prompt = self.workspace.get_full_text_screening_system_prompt()
        ft_user_prompt = self.workspace.get_full_text_screening_user_prompt_template()
        self.assertIn("INDIRECT PROMPT INJECTION GUARD", ft_sys_prompt)
        self.assertIn("<UNTRUSTED_DOCUMENT_CONTENT>", ft_user_prompt)

    def test_all_tokens_revoked_on_password_change(self):
        """Verify that changing password revokes outstanding refresh tokens."""
        refresh = RefreshToken.for_user(self.researcher_user)
        self.client.force_authenticate(user=self.researcher_user)

        change_res = self.client.post("/api/auth/change-password/", {
            "old_password": "ResearcherPassword123!",
            "new_password": "NewSecurePassword2026!",
            "confirm_password": "NewSecurePassword2026!"
        }, format="json")
        self.assertEqual(change_res.status_code, status.HTTP_200_OK)

        # Attempting to refresh using old token must now fail
        refresh_attempt = self.client.post("/api/auth/refresh/", {
            "refresh": str(refresh)
        }, format="json")
        self.assertEqual(refresh_attempt.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cleanup_expired_tokens_task(self):
        """Verify periodic Celery Beat task purging expired blacklisted tokens."""
        from datetime import timedelta
        from django.utils import timezone
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        from research_intelligence.tasks.auxiliary.token_cleanup import cleanup_expired_blacklisted_tokens

        # Create expired token in past
        past_time = timezone.now() - timedelta(days=2)
        ot = OutstandingToken.objects.create(
            user=self.admin_user,
            jti="expired-test-jti",
            token="dummy-expired-token",
            created_at=past_time,
            expires_at=past_time
        )
        BlacklistedToken.objects.create(token=ot)

        res = cleanup_expired_blacklisted_tokens()
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["deleted_blacklisted"], 1)
        self.assertFalse(OutstandingToken.objects.filter(jti="expired-test-jti").exists())

    def test_quota_exceeded_blocks_chat_and_triggers(self):
        """Verify that when workspace quota is exceeded, chat engine and pipeline triggers reject execution."""
        from chat.models import PaperChatSession, PaperChatMessage
        from chat.engine.orchestrator import PaperChatEngine
        from mcp_server.tools.pipeline_runs.triggers import trigger_search_job_logic, trigger_pdf_download_job_logic

        # Exceed workspace tokens limit
        self.workspace.monthly_token_limit = 1000
        self.workspace.tokens_consumed_this_month = 5000
        self.workspace.save(update_fields=['monthly_token_limit', 'tokens_consumed_this_month'])

        # 1. Chat Engine rejection
        session = PaperChatSession.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            title="Quota Test Session"
        )
        msg = PaperChatMessage.objects.create(
            session=session,
            question="Can you summarize this?",
            status="pending"
        )
        engine = PaperChatEngine()
        result = engine.execute(msg)
        self.assertEqual(result["status"], "failed")
        self.assertIn("quota exceeded", result["error"].lower())

        # 2. Trigger Search Job rejection
        search_res = trigger_search_job_logic(self.admin_user, str(self.workspace.id))
        self.assertIn("quota exceeded", search_res.lower())

        # 3. Trigger PDF Download Job rejection
        from research_intelligence.models import PipelineRun
        PipelineRun.objects.create(workspace=self.workspace, status='completed')
        download_res = trigger_pdf_download_job_logic(self.admin_user, workspace_id=str(self.workspace.id))
        self.assertIn("quota exceeded", download_res.lower())

    def test_researcher_cannot_start_or_create_pipeline_run(self):
        """Verify that Researcher cannot start or create pipeline runs (returns 403)."""
        self.client.force_authenticate(user=self.researcher_user)

        # 1. POST /api/pipeline-runs/
        res_create = self.client.post("/api/pipeline-runs/", {
            "workspace_id": str(self.workspace.id),
            "name": "Researcher Run",
        }, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_403_FORBIDDEN)

        # 2. POST /api/pipeline-runs/start/
        res_start = self.client.post("/api/pipeline-runs/start/", {
            "workspace_id": str(self.workspace.id),
            "name": "Researcher Autonomous Run",
        }, format="json")
        self.assertEqual(res_start.status_code, status.HTTP_403_FORBIDDEN)

    def test_researcher_cannot_pause_resume_tick_abort_rerun_trigger_step(self):
        """Verify that Researcher cannot pause, resume, tick, abort, rerun, or trigger steps on a pipeline run."""
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="search"
        )
        self.client.force_authenticate(user=self.researcher_user)

        # 1. Pause
        res_pause = self.client.post(f"/api/pipeline-runs/{run.id}/pause/", format="json")
        self.assertEqual(res_pause.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Resume
        res_resume = self.client.post(f"/api/pipeline-runs/{run.id}/resume/", format="json")
        self.assertEqual(res_resume.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Tick
        res_tick = self.client.post(f"/api/pipeline-runs/{run.id}/tick/", format="json")
        self.assertEqual(res_tick.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Abort
        res_abort = self.client.post(f"/api/pipeline-runs/{run.id}/abort/", format="json")
        self.assertEqual(res_abort.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Rerun from step
        res_rerun = self.client.post(f"/api/pipeline-runs/{run.id}/rerun-from-step/", {"step_name": "search"}, format="json")
        self.assertEqual(res_rerun.status_code, status.HTTP_403_FORBIDDEN)

        # 6. Trigger step
        res_trigger = self.client.post(f"/api/pipeline-runs/{run.id}/trigger-step/", {
            "step_type": "download",
            "limit": 10
        }, format="json")
        self.assertEqual(res_trigger.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_pause_resume_and_rerun_pipeline_run(self):
        """Verify that Admin role has permission to pause and resume pipeline runs."""
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="search"
        )
        self.client.force_authenticate(user=self.admin_user)

        # 1. Pause
        res_pause = self.client.post(f"/api/pipeline-runs/{run.id}/pause/", format="json")
        self.assertEqual(res_pause.status_code, status.HTTP_200_OK)
        run.refresh_from_db()
        self.assertEqual(run.status, "paused")

        # 2. Resume
        res_resume = self.client.post(f"/api/pipeline-runs/{run.id}/resume/", format="json")
        self.assertEqual(res_resume.status_code, status.HTTP_200_OK)
        run.refresh_from_db()
        self.assertEqual(run.status, "running")

    def test_manager_can_start_stop_but_cannot_rerun(self):
        """Verify Manager can start and abort, but cannot rerun from step (Admin only)."""
        self.client.force_authenticate(user=self.manager_user)

        # 1. Start is allowed for Manager
        res_create = self.client.post("/api/pipeline-runs/", {
            "workspace_id": str(self.workspace.id),
            "name": "Manager Run",
        }, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        # 2. Abort is allowed for Manager
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="search"
        )
        res_abort = self.client.post(f"/api/pipeline-runs/{run.id}/abort/", format="json")
        self.assertEqual(res_abort.status_code, status.HTTP_200_OK)

        # 3. Rerun is forbidden for Manager (Admin only)
        res_rerun = self.client.post(f"/api/pipeline-runs/{run.id}/rerun-from-step/", {"step_name": "search"}, format="json")
        self.assertEqual(res_rerun.status_code, status.HTTP_403_FORBIDDEN)



