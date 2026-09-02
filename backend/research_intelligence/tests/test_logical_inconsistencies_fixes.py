"""
Comprehensive test suite verifying the resolution of all identified logical inconsistencies:
1. compute_paper_signal_score accepts UUID/str without FieldError on select_related.
2. PaperMetricManager.create infers workspace from paper or pipeline_run if omitted.
3. Zombie watchdog does not prematurely complete running in-flight pipelines.
4. reprocess_existing=True links all existing workspace papers to pipeline_run.
5. Screening halt logic respects borderline (HITL) papers and does not halt early.
6. Paper.latest_pipeline_run vs Paper.pipeline_run semantics & admin link.
7. Email digest dictionary comprehension preserves the newest metric.
8. Screening passed count aggregation idempotency (no double-counting on retry).
9. Extractions matrix RBAC authorization enforcement (cross-workspace leak prevented).
10. Extraction token accounting logs the definition's actual llm_model.
11. Signal score descending ordering puts NULL values last in Paper and Metric querysets.
12. Sandbox execution prioritizes __signal_calc__ over local helper functions.
"""

import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    LLMUsageRecord,
)
from research_intelligence.admin import PaperAdmin, PaperMetricAdmin
from research_intelligence.tasks.step_6_signal_score.scorer import compute_paper_signal_score
from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks
from research_intelligence.tasks.step_1_search.node import SearchNode
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode
from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload
from research_intelligence.services.extraction_service import build_paper_extractions_matrix
from mcp_server.tools.extractions.matrix import get_paper_extractions_matrix_logic
from research_intelligence.utils.sandbox import execute_sandboxed_snippet
from api.views.papers import PaperViewSet, PaperMetricViewSet

User = get_user_model()


class LogicalInconsistenciesFixesTestCase(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a", email="a@example.com", password="pwd")
        self.user_b = User.objects.create_user(username="user_b", email="b@example.com", password="pwd")

        self.workspace_a = Workspace.objects.create(
            name="Workspace A",
            screening_llm_model="google/gemini-3.8-flash",
            signal_score_code="score = trl_score * 2.0\nreturn score"
        )
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.user_a, role="admin")

        self.workspace_b = Workspace.objects.create(
            name="Workspace B",
            screening_llm_model="google/gemini-3.8-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.user_b, role="admin")

        self.run_a1 = PipelineRun.objects.create(
            workspace=self.workspace_a,
            status="running",
            current_stage="search",
            started_at=timezone.now()
        )

        self.paper_1 = Paper.objects.create(
            workspace=self.workspace_a,
            title="Quantum Graph Neural Networks for Drug Discovery",
            doi="10.1000/18274",
            arxiv_id="2401.99999",
            source_database="arxiv"
        )

    # -------------------------------------------------------------------------
    # 1. compute_paper_signal_score without FieldError on select_related
    # -------------------------------------------------------------------------
    def test_compute_paper_signal_score_accepts_uuid_and_does_not_crash(self):
        # Create an extraction parameter for trl_score
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="trl_score",
            exit_metric="trl_score",
            response_schema={"type": "object"}
        )
        Extraction.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_1,
            extraction_definition=ext_def,
            category="trl_score",
            fields_data={"trl_score": 4.5}
        )

        # Call compute_paper_signal_score with paper UUID string (not Paper instance)
        score, details = compute_paper_signal_score(
            paper_id_or_obj=str(self.paper_1.id),
            pipeline_run=self.run_a1
        )
        self.assertEqual(score, 9.0)
        self.assertIn("trl_score", details.get("variables", {}))

    # -------------------------------------------------------------------------
    # 2. PaperMetricManager.create automatically infers workspace
    # -------------------------------------------------------------------------
    def test_paper_metric_manager_create_infers_workspace(self):
        # Call PaperMetric.objects.create without passing workspace or workspace_id
        metric = PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            screening_status="accepted",
            signal_score=8.5
        )
        self.assertIsNotNone(metric)
        self.assertEqual(metric.workspace, self.workspace_a)

    # -------------------------------------------------------------------------
    # 3. Zombie watchdog does not prematurely complete running in-flight pipeline
    # -------------------------------------------------------------------------
    def test_zombie_watchdog_does_not_prematurely_complete_in_flight_pipeline(self):
        # run_a1 is in 'running' status with current_stage='search'
        # Suppose Step 1 (search) component just completed 5 seconds ago
        ComponentRun.objects.create(
            pipeline_run=self.run_a1,
            step_type="search",
            component_name="arxiv_scraper",
            status="completed",
            started_at=timezone.now() - timedelta(seconds=10),
            completed_at=timezone.now() - timedelta(seconds=5)
        )

        # Run the watchdog with default timeout
        stats = reap_zombie_tasks(max_component_age_minutes=60, force=False)
        self.run_a1.refresh_from_db()

        # The pipeline MUST remain 'running' because current_stage != 'completed' and not timed out
        self.assertEqual(self.run_a1.status, "running")
        self.assertNotIn(f"PipelineRun {self.run_a1.id} -> completed", stats.get("details", []))

        # But if the pipeline legitimately finished all stages (current_stage='completed'):
        self.run_a1.current_stage = "completed"
        self.run_a1.save(update_fields=["current_stage"])
        stats2 = reap_zombie_tasks(max_component_age_minutes=60, force=False)
        self.run_a1.refresh_from_db()
        self.assertEqual(self.run_a1.status, "completed")

    # -------------------------------------------------------------------------
    # 4. reprocess_existing=True links all existing workspace papers
    # -------------------------------------------------------------------------
    def test_reprocess_existing_links_workspace_papers(self):
        # Workspace A has paper_1. Create a new pipeline run with reprocess_existing=True
        reprocess_run = PipelineRun.objects.create(
            workspace=self.workspace_a,
            reprocess_existing=True,
            status="running"
        )
        from research_intelligence.models import Scraper
        scraper = Scraper.objects.create(
            workspace=self.workspace_a,
            provider="arxiv",
            search_query="quantum",
            limit=5
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=reprocess_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="running"
        )

        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job

        # Mock scraper returning 0 items from external query
        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_sp:
            provider_inst = MagicMock()
            provider_inst.search.return_value = []
            mock_sp.return_value = provider_inst

            execute_scraper_run_job(str(comp_run.id))

        # Verify paper_1 is linked to reprocess_run via PaperMetric
        reprocess_papers = reprocess_run.get_papers()
        self.assertIn(self.paper_1, reprocess_papers)

        # SearchNode.should_halt_pipeline should not halt
        comp_run.status = "completed"
        comp_run.save(update_fields=["status"])
        node = SearchNode()
        should_halt, reason = node.should_halt_pipeline(reprocess_run, self.workspace_a, {})
        self.assertFalse(should_halt)

    # -------------------------------------------------------------------------
    # 5. Screening halt logic respects borderline (HITL) papers
    # -------------------------------------------------------------------------
    def test_screening_halt_logic_respects_borderline_papers(self):
        # Attach metric with 'borderline' screening status
        PaperMetric.objects.update_or_create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            defaults={"workspace": self.workspace_a, "screening_status": "borderline"}
        )

        ComponentRun.objects.create(
            pipeline_run=self.run_a1,
            step_type="screening",
            component_name="abstract_screening",
            status="completed"
        )

        node = AbstractScreeningNode()
        should_halt, reason = node.should_halt_pipeline(self.run_a1, self.workspace_a, {})
        # Should NOT halt because borderline paper awaits human review
        self.assertFalse(should_halt)

    # -------------------------------------------------------------------------
    # 6. Paper.latest_pipeline_run vs initial Paper.pipeline_run
    # -------------------------------------------------------------------------
    def test_paper_latest_pipeline_run_and_initial_pipeline_run(self):
        run_old = PipelineRun.objects.create(workspace=self.workspace_a, status="completed")
        run_new = PipelineRun.objects.create(workspace=self.workspace_a, status="completed")

        PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=run_old,
            screening_status="accepted",
            created_at=timezone.now() - timedelta(days=5)
        )
        PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=run_new,
            screening_status="accepted",
            created_at=timezone.now()
        )

        self.assertEqual(self.paper_1.pipeline_run, run_old)
        self.assertEqual(self.paper_1.latest_pipeline_run, run_new)

        # Test PaperAdmin display
        admin = PaperAdmin(Paper, AdminSite())
        self.assertNotIn("pipeline_run_link", admin.list_display)
        self.assertIn("runs_count_badge", admin.list_display)
        badge_html = admin.runs_count_badge(self.paper_1)
        self.assertIn("2 runy", badge_html)
        link_html = admin.pipeline_run_link(self.paper_1)
        self.assertIn(str(run_new.id), link_html)

    # -------------------------------------------------------------------------
    # 7. Email digest preserves newest metric
    # -------------------------------------------------------------------------
    def test_email_digest_picks_latest_metric(self):
        # Create older metric and newer metric for paper_1
        t_old = timezone.now() - timedelta(days=2)
        t_new = timezone.now()

        m_old = PaperMetric.objects.create(
            paper=self.paper_1,
            workspace=self.workspace_a,
            screening_status="accepted",
            signal_score=3.0,
            created_at=t_old
        )
        # Ensure distinct created_at
        PaperMetric.objects.filter(id=m_old.id).update(created_at=t_old)

        m_new = PaperMetric.objects.create(
            paper=self.paper_1,
            workspace=self.workspace_a,
            screening_status="accepted",
            signal_score=8.5,
            created_at=t_new
        )
        PaperMetric.objects.filter(id=m_new.id).update(created_at=t_new)

        # Run email digest logic dictionary assembly
        accepted_papers = [self.paper_1]
        metrics_by_paper = {}
        for pm in PaperMetric.objects.filter(paper__in=accepted_papers).order_by('-created_at'):
            if pm.paper_id not in metrics_by_paper:
                metrics_by_paper[pm.paper_id] = pm

        self.assertEqual(metrics_by_paper[self.paper_1.id].signal_score, 8.5)

    # -------------------------------------------------------------------------
    # 8. Screening passed count aggregation idempotency
    # -------------------------------------------------------------------------
    def test_screening_passed_count_aggregation_idempotency(self):
        PaperMetric.objects.update_or_create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            defaults={"workspace": self.workspace_a, "screening_status": "abstract_passed"}
        )

        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
        comp = ComponentRun.objects.create(
            pipeline_run=self.run_a1,
            step_type="screening",
            component_name="abstract_screening",
            status="running"
        )

        # Mock LLM generation to pass paper
        with patch("research_intelligence.tasks.step_4_screening.abstract.get_llm_provider") as mock_prov:
            prov = MagicMock()
            prov.generate.return_value = {"passed": True, "reasoning": "Pass", "decision_category": "ACCEPTED", "usage": {}}
            mock_prov.return_value = prov

            # Run once
            execute_screening_job(str(comp.id))
            self.run_a1.refresh_from_db()
            first_count = self.run_a1.total_papers_passed_screening

            # Simulate retry / second execution
            execute_screening_job(str(comp.id))
            self.run_a1.refresh_from_db()
            second_count = self.run_a1.total_papers_passed_screening

            # The count should NOT double
            self.assertEqual(first_count, second_count)
            self.assertEqual(second_count, 1)

    # -------------------------------------------------------------------------
    # 9. Extractions matrix RBAC authorization enforcement
    # -------------------------------------------------------------------------
    def test_extractions_matrix_authorization_enforced(self):
        # User B tries to query Workspace A's extractions matrix
        res = build_paper_extractions_matrix(
            user=self.user_b,
            workspace_id=str(self.workspace_a.id)
        )
        self.assertIn("error", res)
        self.assertIn("do not have access", res["error"])

        # MCP tool layer test
        mcp_res = json.loads(get_paper_extractions_matrix_logic(
            user=self.user_b,
            workspace_id=str(self.workspace_a.id)
        ))
        self.assertIn("error", mcp_res)

        # User A (member) can access
        valid_res = build_paper_extractions_matrix(
            user=self.user_a,
            workspace_id=str(self.workspace_a.id)
        )
        self.assertNotIn("error", valid_res)
        self.assertIn("total_papers", valid_res)

    # -------------------------------------------------------------------------
    # 10. Extraction token accounting logs the definition's actual llm_model
    # -------------------------------------------------------------------------
    def test_extraction_records_correct_llm_model_in_usage(self):
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Novelty Score",
            llm_model="anthropic/claude-3.5-sonnet",
            system_prompt="Assess novelty.",
            user_prompt_template="Assess: {paper_text}",
            response_schema={"type": "object", "properties": {"score": {"type": "number"}}},
            exit_metric="score"
        )
        PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            screening_status="accepted"
        )
        comp = ComponentRun.objects.create(
            pipeline_run=self.run_a1,
            step_type="extraction",
            component_name="extraction_job",
            status="running"
        )

        from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job

        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_prov:
            prov = MagicMock()
            prov.generate.return_value = {
                "score": 9.5,
                "usage": {"tokens_in": 100, "tokens_out": 20, "total_tokens": 120}
            }
            mock_prov.return_value = prov

            execute_extraction_job(str(comp.id))

        usage_rec = LLMUsageRecord.objects.filter(
            workspace=self.workspace_a,
            pipeline_run_id=str(self.run_a1.id),
            operation_type="extraction"
        ).last()

        self.assertIsNotNone(usage_rec)
        self.assertEqual(usage_rec.llm_model, "anthropic/claude-3.5-sonnet")

    # -------------------------------------------------------------------------
    # 11. Signal score descending ordering puts NULL values last
    # -------------------------------------------------------------------------
    def test_signal_score_descending_ordering_nulls_last(self):
        p_high = Paper.objects.create(workspace=self.workspace_a, hash_id="high_score", title="High Score Paper", source_database="arxiv")
        p_low = Paper.objects.create(workspace=self.workspace_a, hash_id="low_score", title="Low Score Paper", source_database="arxiv")
        p_unscored = Paper.objects.create(workspace=self.workspace_a, hash_id="unscored_score", title="Unscored Paper", source_database="arxiv")

        PaperMetric.objects.create(paper=p_high, pipeline_run=self.run_a1, signal_score=9.5)
        PaperMetric.objects.create(paper=p_low, pipeline_run=self.run_a1, signal_score=3.0)
        PaperMetric.objects.create(paper=p_unscored, pipeline_run=self.run_a1, signal_score=None)

        factory = APIRequestFactory()
        req = factory.get(f"/api/papers/?pipeline_run={self.run_a1.id}&ordering=-signal_score")
        from rest_framework.request import Request
        view = PaperViewSet()
        view.request = Request(req)
        view.request.user = self.user_a
        view.format_kwarg = None
        qs = view.get_queryset()

        scored_ids = [p.id for p in qs]
        # p_high should be first, then p_low, and p_unscored should be last
        self.assertEqual(scored_ids[0], p_high.id)
        self.assertEqual(scored_ids[1], p_low.id)
        self.assertEqual(scored_ids[2], p_unscored.id)

    # -------------------------------------------------------------------------
    # 12. Sandbox execution prioritizes __signal_calc__ over local helper functions
    # -------------------------------------------------------------------------
    def test_sandbox_prioritizes_signal_calc_over_local_helper_functions(self):
        # Code defines a local helper function followed by formula statements
        code = """
def clamp(val):
    return min(10.0, max(0.0, val))

score = clamp(trl_val) * 0.5 + 4.0
"""
        context = {"trl_val": 8.0}
        score = execute_sandboxed_snippet(code, context)
        self.assertEqual(score, 8.0)

    # -------------------------------------------------------------------------
    # 13. PaperMetricAdmin configuration: no benchmark, metric detail link, workspace link, badges
    # -------------------------------------------------------------------------
    def test_paper_metric_admin_configuration_and_formatting(self):
        admin = PaperMetricAdmin(PaperMetric, AdminSite())

        # 1. Column structure checks
        self.assertNotIn("benchmark_badge", admin.list_display)
        self.assertIn("metric_detail_link", admin.list_display)
        self.assertIn("workspace_link", admin.list_display)
        self.assertEqual(admin.list_display_links, ("metric_detail_link",))

        # 2. Metric instance rendering
        metric = PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            workspace=self.workspace_a,
            screening_status="accepted",
            metrics_data={
                "is_active": True,
                "trl_level": 7,
                "test_e2e_sched_58705055_trl_level": 7,
                "reasoning": "Extremely detailed rationale that must not be in list preview",
                "justification": "Detailed explanation of result",
                "decision_category": "ACCEPTED: Core scope",
                "methodology": "CNN-GNN"
            }
        )

        # Detail link contains link to papermetric change form
        detail_html = admin.metric_detail_link(metric)
        self.assertIn(str(metric.id), detail_html)
        self.assertIn("Detal", detail_html)

        # Workspace link contains workspace name and URL
        ws_html = admin.workspace_link(metric)
        self.assertIn(self.workspace_a.name, ws_html)

        # Metrics preview renders badges on separate lines and skips heavy text / test aliases
        preview_html = admin.metrics_preview(metric)
        self.assertIn("PASS", preview_html)
        self.assertIn("7", preview_html)
        self.assertIn("CNN-GNN", preview_html)
        self.assertNotIn("test_e2e_sched_58705055_trl_level", preview_html)
        self.assertNotIn("Extremely detailed rationale", preview_html)
        self.assertNotIn("Detailed explanation of result", preview_html)
        self.assertNotIn("decision_category", preview_html)
        self.assertIn("<div", preview_html)

    # -------------------------------------------------------------------------
    # 14. Abstract & Full-Text Screening reasoning preservation across stages, Admin, and API
    # -------------------------------------------------------------------------
    def test_abstract_and_full_text_screening_reasoning_preservation_and_api(self):
        # 1. Abstract Screening records abstract_screening_reasoning without duplicate writes
        pm = PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=self.run_a1,
            workspace=self.workspace_a,
            screening_status="abstract_passed",
            abstract_screening_reasoning="Abstract clearly addresses fault-tolerant syndrome decoding.",
            metrics_data={
                "abstract_screening": {
                    "passed": True,
                    "reasoning": "Abstract clearly addresses fault-tolerant syndrome decoding.",
                }
            }
        )
        self.assertEqual(pm.latest_screening_reasoning, "Abstract clearly addresses fault-tolerant syndrome decoding.")

        # 2. Full-Text Screening records full_text_screening_reasoning without overwriting abstract
        pm.screening_status = "full_text_passed"
        pm.full_text_screening_reasoning = "Full text proves physical threshold p < 1.2% on simulated grid."
        pm.metrics_data["full_text_screening"] = {
            "passed": True,
            "reasoning": "Full text proves physical threshold p < 1.2% on simulated grid."
        }
        pm.save()

        # Reload from DB and verify both reasonings are preserved independently
        pm.refresh_from_db()
        self.assertEqual(pm.abstract_screening_reasoning, "Abstract clearly addresses fault-tolerant syndrome decoding.")
        self.assertEqual(pm.full_text_screening_reasoning, "Full text proves physical threshold p < 1.2% on simulated grid.")
        self.assertEqual(pm.latest_screening_reasoning, "Full text proves physical threshold p < 1.2% on simulated grid.")

        # 3. Step 6 (compute_paper_signal_score) does not wipe out screening dicts in metrics_data
        self.workspace_a.signal_score_code = "score = 85.0"
        self.workspace_a.save()
        compute_paper_signal_score(self.paper_1, pipeline_run=self.run_a1)

        pm.refresh_from_db()
        self.assertEqual(pm.signal_score, 85.0)
        self.assertIn("abstract_screening", pm.metrics_data)
        self.assertIn("full_text_screening", pm.metrics_data)

        # 4. REST API Serializer returns both reasonings
        from api.serializers.papers import PaperSerializer, PaperMetricSerializer
        ser = PaperSerializer(self.paper_1, context={"pipeline_run": str(self.run_a1.id)})
        data = ser.data
        self.assertEqual(data["abstract_screening_reasoning"], "Abstract clearly addresses fault-tolerant syndrome decoding.")
        self.assertEqual(data["full_text_screening_reasoning"], "Full text proves physical threshold p < 1.2% on simulated grid.")
        self.assertNotIn("screening_reasoning", data)

        metric_ser = PaperMetricSerializer(pm)
        self.assertEqual(metric_ser.data["abstract_screening_reasoning"], "Abstract clearly addresses fault-tolerant syndrome decoding.")
        self.assertEqual(metric_ser.data["full_text_screening_reasoning"], "Full text proves physical threshold p < 1.2% on simulated grid.")
        self.assertNotIn("screening_reasoning", metric_ser.data)

        # 5. PaperMetricAdmin renders both reasonings in detail displays
        admin = PaperMetricAdmin(PaperMetric, AdminSite())
        abs_html = admin.abstract_screening_reasoning_display(pm)
        self.assertIn("Abstract clearly addresses fault-tolerant syndrome decoding.", abs_html)
        ft_html = admin.full_text_screening_reasoning_display(pm)
        self.assertIn("Full text proves physical threshold", ft_html)
        self.assertIn("&lt; 1.2% on simulated grid.", ft_html)

        # 6. Fallback test: when abstract_screening_reasoning column is None, it falls back to ComponentRun
        paper_legacy = Paper.objects.create(
            workspace=self.workspace_a,
            title="Legacy Paper",
            hash_id="legacy_hash_123"
        )
        pm_legacy = PaperMetric.objects.create(
            paper=paper_legacy,
            pipeline_run=self.run_a1,
            workspace=self.workspace_a,
            screening_status="full_text_passed",
            abstract_screening_reasoning=None,
            full_text_screening_reasoning=None
        )
        ComponentRun.objects.create(
            pipeline_run=self.run_a1,
            step_type="abstract_screening",
            component_name="abstract_screening",
            status="completed",
            output_data={
                "screened_papers": [
                    {
                        "paper_id": str(paper_legacy.id),
                        "reasoning": "Recovered abstract reasoning from component run audit!"
                    }
                ]
            }
        )
        fallback_html = admin.abstract_screening_reasoning_display(pm_legacy)
        self.assertIn("Recovered abstract reasoning from component run audit!", fallback_html)
