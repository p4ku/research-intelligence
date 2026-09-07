from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
)

User = get_user_model()

RUN_BLOBS = ('step_history', 'stage_results')
RUN_KEPT = ('configuration_override', 'period', 'total_papers_screened')


class ListSerializersTestCase(TestCase):
    """
    The list faces of runs and papers stop growing with run length / run
    count; the detail faces (and the create response) keep everything.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="list_user",
            email="list@schwarz.de",
            password="securepassword123!",
        )
        self.workspace = Workspace.objects.create(name="List Serializers Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run 1",
            status="completed",
            triggered_by=self.user,
            configuration_override={"start_date": "2026-08-01", "end_date": "2026-08-07"},
            stage_results={"search": {"papers_found": 12}},
            step_history=[{"step": "search", "status": "completed"}],
        )
        self.run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run 2",
            status="completed",
            triggered_by=self.user,
            configuration_override={"n_last_days": 7},
            stage_results={"search": {"papers_found": 3}},
            step_history=[{"step": "search", "status": "completed"}],
        )

        self.paper_multi = Paper.objects.create(
            workspace=self.workspace,
            title="Evaluated in both runs",
            hash_id="hash_multi",
            doi="10.1000/multi",
            authors="A. Author",
            abstract="Two runs looked at this one.",
            source_database="arxiv",
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.run_1,
            workspace=self.workspace,
            screening_status="borderline",
            signal_score=40.0,
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.run_2,
            workspace=self.workspace,
            screening_status="accepted",
            signal_score=90.0,
        )

        self.paper_single = Paper.objects.create(
            workspace=self.workspace,
            title="Evaluated in run 1 only",
            hash_id="hash_single",
            doi="10.1000/single",
            authors="B. Author",
            abstract="One run looked at this one.",
            source_database="arxiv",
        )
        PaperMetric.objects.create(
            paper=self.paper_single,
            pipeline_run=self.run_1,
            workspace=self.workspace,
            screening_status="rejected",
            signal_score=10.0,
        )

        self.paper_bare = Paper.objects.create(
            workspace=self.workspace,
            title="No metrics yet",
            hash_id="hash_bare",
            doi="10.1000/bare",
            authors="C. Author",
            abstract="Freshly ingested.",
            source_database="arxiv",
        )

    @staticmethod
    def _rows(res):
        body = res.json()
        return body["results"] if isinstance(body, dict) and "results" in body else body

    # (a) list rows drop the two blobs and keep the scalars
    def test_pipeline_run_list_rows_drop_the_blobs(self):
        res = self.client.get("/api/pipeline-runs/")
        self.assertEqual(res.status_code, 200)
        rows = self._rows(res)
        self.assertEqual(len(rows), 2)
        for row in rows:
            for blob in RUN_BLOBS:
                self.assertNotIn(blob, row)
            for kept in RUN_KEPT:
                self.assertIn(kept, row)
        row_1 = next(r for r in rows if r["id"] == str(self.run_1.id))
        self.assertEqual(row_1["configuration_override"], {"start_date": "2026-08-01", "end_date": "2026-08-07"})

        # The paginated face uses the same serializer.
        res_pag = self.client.get("/api/pipeline-runs/?page=1&page_size=1")
        self.assertEqual(res_pag.status_code, 200)
        for row in res_pag.json()["results"]:
            for blob in RUN_BLOBS:
                self.assertNotIn(blob, row)

    # (b) detail keeps both blobs
    def test_pipeline_run_detail_keeps_the_blobs(self):
        res = self.client.get(f"/api/pipeline-runs/{self.run_1.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["stage_results"], {"search": {"papers_found": 12}})
        self.assertEqual(body["step_history"], [{"step": "search", "status": "completed"}])
        self.assertIn("component_runs", body)

    # (c) create answers with the full base serializer
    def test_pipeline_run_create_keeps_the_blobs(self):
        res = self.client.post(
            "/api/pipeline-runs/",
            {"workspace_id": str(self.workspace.id), "name": "Created", "n_last_days": 3},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        for blob in RUN_BLOBS:
            self.assertIn(blob, body)
        self.assertEqual(body["configuration_override"], {"n_last_days": 3})
        self.assertNotIn("component_runs", body)

    # (d) paper list rows carry only the target run's metric
    def test_paper_list_rows_carry_one_metric(self):
        res = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}")
        self.assertEqual(res.status_code, 200)
        rows = self._rows(res)
        self.assertEqual(len(rows), 3)
        by_id = {r["id"]: r for r in rows}

        multi = by_id[str(self.paper_multi.id)]
        self.assertEqual(len(multi["metrics"]), 1)
        self.assertEqual(multi["metrics"][0]["pipeline_run"], multi["pipeline_run"])
        self.assertEqual(multi["pipeline_run"], str(self.run_2.id))
        self.assertEqual(multi["metrics"][0]["signal_score"], multi["signal_score"])
        self.assertEqual(multi["signal_score"], 90.0)

        # Scored by run_1 only while the workspace's latest run is run_2: the
        # row's pipeline_run must be the run its one metric belongs to, or the
        # frontend's find-by-pipeline_run misses it.
        single = by_id[str(self.paper_single.id)]
        self.assertEqual(len(single["metrics"]), 1)
        self.assertEqual(single["metrics"][0]["pipeline_run"], str(self.run_1.id))
        self.assertEqual(single["pipeline_run"], str(self.run_1.id))

        bare = by_id[str(self.paper_bare.id)]
        self.assertEqual(bare["metrics"], [])
        self.assertEqual(bare["screening_status"], "pending")

    # (e) detail returns every metric
    def test_paper_detail_returns_every_metric(self):
        res = self.client.get(f"/api/papers/{self.paper_multi.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["metrics"]), 2)
        self.assertEqual(
            {m["pipeline_run"] for m in body["metrics"]},
            {str(self.run_1.id), str(self.run_2.id)},
        )

    # (f) the workspace papers action agrees with the papers list
    def test_workspace_papers_action_matches_paper_list(self):
        res = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/")
        self.assertEqual(res.status_code, 200)
        rows = self._rows(res)
        self.assertEqual(len(rows), 3)
        multi = next(r for r in rows if r["id"] == str(self.paper_multi.id))
        self.assertEqual(len(multi["metrics"]), 1)
        self.assertEqual(multi["metrics"][0]["pipeline_run"], multi["pipeline_run"])
        self.assertEqual(multi["pipeline_run"], str(self.run_2.id))

        res_pag = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/?page=1&page_size=10")
        self.assertEqual(res_pag.status_code, 200)
        multi_pag = next(r for r in res_pag.json()["results"] if r["id"] == str(self.paper_multi.id))
        self.assertEqual(len(multi_pag["metrics"]), 1)

    # (g) a run-scoped list still answers with that run's metric only
    def test_paper_list_scoped_to_a_run_keeps_that_runs_metric(self):
        res = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}")
        self.assertEqual(res.status_code, 200)
        rows = self._rows(res)
        self.assertEqual(len(rows), 2)
        multi = next(r for r in rows if r["id"] == str(self.paper_multi.id))
        self.assertEqual(len(multi["metrics"]), 1)
        self.assertEqual(multi["metrics"][0]["pipeline_run"], str(self.run_1.id))
        self.assertEqual(multi["pipeline_run"], str(self.run_1.id))
        self.assertEqual(multi["signal_score"], 40.0)
        self.assertEqual(multi["screening_status"], "borderline")

    def test_list_metric_matches_the_metric_serializer(self):
        from api.serializers.papers import PaperListSerializer, PaperMetricSerializer, PaperSerializer

        papers = list(
            Paper.objects.filter(id__in=[self.paper_multi.id, self.paper_single.id])
            .order_by("hash_id")
            .prefetch_related("metrics")
        )
        context = {"pipeline_run_id": str(self.run_1.id)}
        rows = PaperListSerializer(papers, many=True, context=context).data
        for paper, row in zip(papers, rows):
            target = PaperSerializer(paper, context=context)._get_target_metric(paper)
            self.assertEqual(row["metrics"], [PaperMetricSerializer(target).data])
        # The shared child is one per list, not one per row.
        many = PaperListSerializer(papers, many=True, context=context)
        many.data
        self.assertIsInstance(many._metric_child, PaperMetricSerializer)
        self.assertFalse(hasattr(many.child, "_metric_child"))

    def test_list_serializers_do_not_add_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from api.serializers.papers import PaperListSerializer

        # Papers with at least one metric: the metric-less fallback to the
        # workspace's latest run is a query in the base serializer too.
        papers = list(
            Paper.objects.filter(id__in=[self.paper_multi.id, self.paper_single.id]).prefetch_related("metrics")
        )
        with CaptureQueriesContext(connection) as ctx:
            data = PaperListSerializer(
                papers, many=True, context={"pipeline_run_id": str(self.run_1.id)}
            ).data
            self.assertEqual(len(data), 2)
            self.assertEqual([len(p["metrics"]) for p in data], [1, 1])
        self.assertEqual(len(ctx.captured_queries), 0)
