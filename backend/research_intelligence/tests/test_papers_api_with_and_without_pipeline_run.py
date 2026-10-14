import uuid
from decimal import Decimal
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
from api.serializers.papers import PaperSerializer

User = get_user_model()


class PapersApiWithAndWithoutPipelineRunTestCase(TestCase):
    """
    Dedicated test suite validating that /api/papers/ works seamlessly:
    1. WITH an explicit pipeline_run UUID.
    2. WITH pipeline_run=latest.
    3. WITHOUT any pipeline_run parameter (workspace-level and global corpus).
    4. When papers have NO metrics attached (freshly scraped or unlinked).
    5. On /api/workspaces/{id}/papers/ endpoint with and without pipeline_run.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="contract_user",
            email="contract@schwarz.de",
            password="securepassword123!"
        )
        self.workspace = Workspace.objects.create(name="Quantum NLP Contract Workspace")
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create two distinct pipeline runs
        self.older_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Older Run 2026-01",
            status="completed"
        )
        self.newer_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Newer Run 2026-02",
            status="completed"
        )

        # Paper 1: Evaluated in BOTH runs with different metrics
        self.paper_multi = Paper.objects.create(
            workspace=self.workspace,
            title="Quantum Convolutional Networks for Materials",
            hash_id="hash_multi_1",
            doi="10.1000/qcn.1",
            arxiv_id="2601.00001",
            authors="Alice Q., Bob N.",
            abstract="Quantum convolutional networks...",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.older_run,
            workspace=self.workspace,
            screening_status="borderline",
            abstract_screening_reasoning="Older abstract reasoning: marginal novelty.",
            signal_score=45.0
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.newer_run,
            workspace=self.workspace,
            screening_status="accepted",
            abstract_screening_reasoning="Newer abstract reasoning: accepted.",
            full_text_screening_reasoning="Newer full-text reasoning: verified experimental results.",
            signal_score=88.5
        )

        # Paper 2: Only evaluated in older run
        self.paper_older_only = Paper.objects.create(
            workspace=self.workspace,
            title="Superconducting Qubit Scalability Limits",
            hash_id="hash_older_2",
            doi="10.1000/squbit.2",
            authors="Carol T.",
            abstract="Limits of superconducting qubits...",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=self.paper_older_only,
            pipeline_run=self.older_run,
            workspace=self.workspace,
            screening_status="rejected",
            abstract_screening_reasoning="Rejected: does not meet TRL 4.",
            signal_score=15.0
        )

        # Paper 3: Freshly ingested, NO PaperMetric attached at all
        self.paper_unprocessed = Paper.objects.create(
            workspace=self.workspace,
            title="Topological Braiding in Nanowires",
            hash_id="hash_unprocessed_3",
            doi="10.1000/nanowire.3",
            authors="Dave N.",
            abstract="Braiding operations in Majorana wires...",
            source_database="arxiv"
        )

    def test_1_query_with_explicit_pipeline_run(self):
        """
        WITH pipeline_run=<older_run.id>:
        - Returns only papers evaluated in that run (paper_multi and paper_older_only).
        - Excludes papers not in that run (paper_unprocessed).
        - Serializes run-specific scores and reasonings.
        """
        res = self.client.get(f"/api/papers/?pipeline_run={self.older_run.id}")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)

        p_multi = next(p for p in items if p["id"] == str(self.paper_multi.id))
        self.assertEqual(p_multi["pipeline_run"], str(self.older_run.id))
        self.assertEqual(p_multi["screening_status"], "borderline")
        self.assertEqual(p_multi["screening_reasoning"], "Older abstract reasoning: marginal novelty.")
        self.assertEqual(p_multi["signal_score"], 45.0)

        # WITH pipeline_run=<newer_run.id>:
        res_newer = self.client.get(f"/api/papers/?pipeline_run={self.newer_run.id}")
        self.assertEqual(res_newer.status_code, 200)
        items_newer = res_newer.json()
        self.assertEqual(len(items_newer), 1)
        p_newer = items_newer[0]
        self.assertEqual(p_newer["id"], str(self.paper_multi.id))
        self.assertEqual(p_newer["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_newer["screening_status"], "accepted")
        self.assertEqual(p_newer["screening_reasoning"], "Newer full-text reasoning: verified experimental results.")
        self.assertEqual(p_newer["signal_score"], 88.5)

    def test_2_query_with_pipeline_run_latest(self):
        """
        WITH pipeline_run=latest:
        - Automatically resolves to self.newer_run (the latest completed run).
        - Returns matching papers with metrics for that latest run.
        """
        res = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}&pipeline_run=latest")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item["id"], str(self.paper_multi.id))
        self.assertEqual(item["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(item["screening_status"], "accepted")
        self.assertEqual(item["signal_score"], 88.5)

    def test_3_query_without_pipeline_run_resolves_contract(self):
        """
        WITHOUT pipeline_run:
        - Returns ALL workspace papers (3 papers: multi, older_only, unprocessed).
        - Every paper has a non-null, valid UUID string for 'pipeline_run'.
        - 'screening_reasoning' key is always present (string or null, never undefined).
        - Multi-evaluated paper picks up the latest run's metric.
        - Unprocessed paper falls back to the workspace's latest valid run ID.
        """
        res = self.client.get("/api/papers/")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)

        for p in items:
            # Crucial frontend contract assertions:
            self.assertIn("pipeline_run", p)
            self.assertIn("pipeline_run_id", p)
            self.assertIn("run_id", p)
            self.assertIn("screening_reasoning", p)

            # pipeline_run must NOT be null or empty; must parse as valid UUID
            pr_val = p["pipeline_run"]
            self.assertIsNotNone(pr_val)
            self.assertNotEqual(pr_val, "")
            parsed_uuid = uuid.UUID(str(pr_val))
            self.assertTrue(parsed_uuid)

            # pipeline_run_id and run_id match pipeline_run
            self.assertEqual(p["pipeline_run_id"], pr_val)
            self.assertEqual(p["run_id"], pr_val)

        # Check paper_multi resolves to newest run's metric
        p_multi = next(p for p in items if p["id"] == str(self.paper_multi.id))
        self.assertEqual(p_multi["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_multi["screening_status"], "accepted")
        self.assertEqual(p_multi["signal_score"], 88.5)
        self.assertEqual(p_multi["screening_reasoning"], "Newer full-text reasoning: verified experimental results.")

        # Check paper_unprocessed (no metrics) falls back to latest run ID and status 'pending'
        p_unproc = next(p for p in items if p["id"] == str(self.paper_unprocessed.id))
        self.assertEqual(p_unproc["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_unproc["screening_status"], "pending")
        self.assertIsNone(p_unproc["screening_reasoning"])
        self.assertIsNone(p_unproc["signal_score"])

    def test_4_workspace_papers_endpoint_with_and_without_pipeline_run(self):
        """
        Tests the /api/workspaces/{id}/papers/ action:
        - Without ?pipeline_run: returns all 3 papers for this workspace.
        - With ?pipeline_run: returns filtered papers.
        """
        # Without pipeline_run
        res_all = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/")
        self.assertEqual(res_all.status_code, 200)
        items_all = res_all.json()
        self.assertEqual(len(items_all), 3)

        # With pipeline_run
        res_older = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/?pipeline_run={self.older_run.id}")
        self.assertEqual(res_older.status_code, 200)
        items_older = res_older.json()
        self.assertEqual(len(items_older), 2)

    def test_5_scorecard_and_component_runs_filtering(self):
        """
        Tests the /api/papers/{id}/scorecard/ endpoint with pipeline_run scoping,
        extraction definitions, facts decomposition, narrative report, and component-runs filtering.
        """
        from research_intelligence.models import ComponentRun, Extraction, ExtractionDefinition, NarrativeReport
        c_run = ComponentRun.objects.create(
            pipeline_run=self.newer_run,
            step_type="search",
            component_name="arXiv Ingest",
            status="completed",
        )

        # Setup an ExtractionDefinition and Extraction for Risk & Affiliation Flagging
        risk_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation Flagging",
            system_prompt="Extract risk and affiliation details",
            user_prompt_template="Analyze {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "schwarz_ecosystem_affiliation": {"type": "string"},
                    "gdpr_concerns": {"type": "string"},
                    "author_affiliation": {"type": "string"},
                }
            },
            exit_metrics="schwarz_ecosystem_affiliation, gdpr_concerns",
            is_active=True
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper_multi,
            extraction_definition=risk_def,
            category="risk_and_affiliation",
            fields_data={
                "schwarz_ecosystem_affiliation": "NO (No matching institutions)",
                "gdpr_concerns": "NO (No personal or sensitive data processing involved)",
                "author_affiliation": "North Carolina State University",
                "risk_score": 15.0,
                "risk_score_assessment": "Low enterprise risk profile.",
            },
            confidence_score=0.96,
            validation_status="pass",
        )

        # Extraction Definition WITH postprocessing code (Rule 2)
        fit_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            response_schema={
                "type": "object",
                "properties": {
                    "technical_score": {"type": "number"},
                    "enterprise_score": {"type": "number"},
                }
            },
            exit_metrics="technical_score, enterprise_score",
            postprocessing_code="""
schwarz_fit_postprocessed = (technical_score * 0.7) + (enterprise_score * 0.3)
""",
            is_active=True
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper_multi,
            extraction_definition=fit_def,
            category="schwarz_fit",
            fields_data={
                "technical_score": 80,
                "enterprise_score": 90,
                "schwarz_fit_postprocessed": 83.0,
                "schwarz_fit_computed": 83.0,
            },
            confidence_score=0.98,
            validation_status="pass",
        )

        # Setup NarrativeReport for newer_run
        NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=self.newer_run,
            title="Weekly Executive Briefing - 2026-02",
            content_markdown="### Executive Summary\nQuantum computing advances show noise resilience...",
        )

        # 1. Test scorecard endpoint without params (defaults to latest/newer run)
        res_card = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/")
        self.assertEqual(res_card.status_code, 200)
        data = res_card.json()
        self.assertIn("workspace", data)
        self.assertIn("paper", data)
        self.assertIn("narrative_report", data)
        self.assertIn("extractions", data)
        self.assertIn("metric", data)

        self.assertEqual(data["paper"]["id"], str(self.paper_multi.id))
        self.assertEqual(data["paper"]["title"], self.paper_multi.title)
        self.assertEqual(data["paper"]["signal_score"], 88.5)
        self.assertEqual(data["paper"]["screening_status"], "accepted")
        self.assertEqual(data["narrative_report"]["title"], "Weekly Executive Briefing - 2026-02")
        self.assertIn("Quantum computing advances", data["narrative_report"]["content_markdown"])

        # Verify dynamic schemas & exit metrics in definitions
        self.assertIn("definitions", data)
        risk_def_res = next((d for d in data["definitions"] if d["id"] == str(risk_def.id)), None)
        self.assertIsNotNone(risk_def_res)
        self.assertEqual(risk_def_res["name"], "Risk and Affiliation Flagging")
        self.assertIn("properties", risk_def_res["response_schema"])
        self.assertEqual(risk_def_res["exit_metrics"], ["schwarz_ecosystem_affiliation", "gdpr_concerns"])
        # Rule 1 definition keys
        self.assertFalse(risk_def_res["has_postprocessing"])
        self.assertEqual(risk_def_res["primary_metric_key"], "schwarz_ecosystem_affiliation")
        self.assertEqual(risk_def_res["main_metric_key"], "schwarz_ecosystem_affiliation")
        self.assertEqual(risk_def_res["secondary_metric_keys"], ["gdpr_concerns"])
        self.assertEqual(risk_def_res["auxiliary_metric_keys"], ["gdpr_concerns"])

        # Rule 2 definition keys
        fit_def_res = next((d for d in data["definitions"] if d["id"] == str(fit_def.id)), None)
        self.assertIsNotNone(fit_def_res)
        self.assertTrue(fit_def_res["has_postprocessing"])
        self.assertEqual(fit_def_res["primary_metric_key"], "schwarz_fit_postprocessed")
        self.assertEqual(fit_def_res["main_metric_key"], "schwarz_fit_postprocessed")
        self.assertEqual(fit_def_res["secondary_metric_keys"], ["technical_score", "enterprise_score"])
        self.assertEqual(fit_def_res["auxiliary_metric_keys"], ["technical_score", "enterprise_score"])

        # Verify unflattened extractions list and structured metrics
        self.assertEqual(len(data["extractions"]), 2)
        ext_risk = next(e for e in data["extractions"] if e["definition"]["name"] == "Risk and Affiliation Flagging")
        self.assertEqual(ext_risk["exit_metric"], "NO (No matching institutions)")
        self.assertEqual(ext_risk["fields_data"]["schwarz_ecosystem_affiliation"], "NO (No matching institutions)")
        self.assertEqual(ext_risk["fields_data"]["gdpr_concerns"], "NO (No personal or sensitive data processing involved)")
        self.assertEqual(ext_risk["fields_data"]["risk_score"], 15.0)

        # Rule 1 Extraction verification (Only exit metrics: 1st is primary, rest are secondary)
        self.assertFalse(ext_risk["has_postprocessing"])
        self.assertEqual(ext_risk["primary_metric"]["key"], "schwarz_ecosystem_affiliation")
        self.assertEqual(ext_risk["primary_metric"]["raw"], "NO (No matching institutions)")
        self.assertEqual(ext_risk["primary_metric"]["source"], "exit_metric")
        self.assertEqual(ext_risk["main_metric"]["key"], "schwarz_ecosystem_affiliation")
        self.assertEqual(len(ext_risk["secondary_metrics"]), 1)
        self.assertEqual(ext_risk["secondary_metrics"][0]["key"], "gdpr_concerns")
        self.assertEqual(ext_risk["secondary_metrics"][0]["raw"], "NO (No personal or sensitive data processing involved)")
        self.assertEqual(ext_risk["secondary_metrics"][0]["source"], "exit_metric")
        self.assertEqual(len(ext_risk["auxiliary_metrics"]), 1)
        self.assertEqual(ext_risk["auxiliary_metrics"][0]["key"], "gdpr_concerns")

        # Rule 2 Extraction verification (Postprocessing code: postprocessed is primary, all exit metrics are secondary)
        ext_fit = next(e for e in data["extractions"] if e["definition"]["name"] == "Schwarz Fit")
        self.assertTrue(ext_fit["has_postprocessing"])
        self.assertEqual(ext_fit["exit_metric"], "83.0")
        self.assertEqual(ext_fit["primary_metric"]["key"], "schwarz_fit_postprocessed")
        self.assertEqual(ext_fit["primary_metric"]["value"], 83)
        self.assertEqual(ext_fit["primary_metric"]["source"], "postprocessing")
        self.assertEqual(ext_fit["main_metric"]["key"], "schwarz_fit_postprocessed")
        self.assertEqual(len(ext_fit["secondary_metrics"]), 2)
        sec_keys = [sm["key"] for sm in ext_fit["secondary_metrics"]]
        self.assertEqual(sec_keys, ["technical_score", "enterprise_score"])
        self.assertEqual(ext_fit["secondary_metrics"][0]["value"], 80)
        self.assertEqual(ext_fit["secondary_metrics"][1]["value"], 90)
        self.assertEqual(len(ext_fit["auxiliary_metrics"]), 2)

        # Verify paper.dimensions structure
        dim_fit = next(d for d in data["paper"]["dimensions"] if d["name"] == "Schwarz Fit")
        self.assertTrue(dim_fit["has_postprocessing"])
        self.assertEqual(dim_fit["value"], 83)
        self.assertEqual(dim_fit["primary_metric"]["key"], "schwarz_fit_postprocessed")
        self.assertEqual(len(dim_fit["secondary_metrics"]), 2)

        # 1b. Test nested 1-key dictionary unpacking (e.g. return {"schwarz_fit_postprocessed": final_score})
        ext_fit_model = Extraction.objects.get(id=ext_fit["id"])
        ext_fit_model.fields_data = {
            "technical_score": 80,
            "enterprise_score": 90,
            "schwarz_fit_postprocessed": {
                "schwarz_fit_postprocessed": 87.5
            }
        }
        ext_fit_model.save()
        res_unpacked = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/")
        data_unpacked = res_unpacked.json()
        ext_unpacked = next(e for e in data_unpacked["extractions"] if e["definition"]["name"] == "Schwarz Fit")
        self.assertEqual(ext_unpacked["primary_metric"]["value"], 87.5)
        self.assertEqual(ext_unpacked["primary_metric"]["raw"], "87.5")
        self.assertEqual(ext_unpacked["exit_metric"], "87.5")

        # 1c. Test multi-key postprocessing output (>1 key-value: all extra keys are secondary metrics)
        ext_fit_model.fields_data = {
            "technical_score": 80,
            "enterprise_score": 90,
            "schwarz_fit_postprocessed": 85.0,
            "confidence_level": 0.95,
            "fit_tier": "Tier 1",
        }
        ext_fit_model.save()
        res_multi_sec = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/")
        data_multi_sec = res_multi_sec.json()
        ext_multi = next(e for e in data_multi_sec["extractions"] if e["definition"]["name"] == "Schwarz Fit")
        self.assertEqual(ext_multi["primary_metric"]["value"], 85.0)
        # All extra postprocessing keys + all exit metrics are in secondary metrics
        sec_keys_multi = [sm["key"] for sm in ext_multi["secondary_metrics"]]
        self.assertIn("confidence_level", sec_keys_multi)
        self.assertIn("fit_tier", sec_keys_multi)
        self.assertIn("technical_score", sec_keys_multi)
        self.assertIn("enterprise_score", sec_keys_multi)
        self.assertEqual(len(ext_multi["secondary_metrics"]), 4)

        # 1d. Test multi-key postprocessing where none is named _postprocessed (all are secondary metrics)
        ext_fit_model.fields_data = {
            "technical_score": 80,
            "enterprise_score": 90,
            "sub_metric_alpha": 15,
            "sub_metric_beta": 25,
        }
        ext_fit_model.save()
        res_no_post_key = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/")
        data_no_post_key = res_no_post_key.json()
        ext_no_post = next(e for e in data_no_post_key["extractions"] if e["definition"]["name"] == "Schwarz Fit")
        # All are secondary metrics:
        self.assertIsNone(ext_no_post["primary_metric"]["value"])
        sec_keys_all = [sm["key"] for sm in ext_no_post["secondary_metrics"]]
        self.assertIn("sub_metric_alpha", sec_keys_all)
        self.assertIn("sub_metric_beta", sec_keys_all)
        self.assertIn("technical_score", sec_keys_all)
        self.assertIn("enterprise_score", sec_keys_all)
        self.assertEqual(len(ext_no_post["secondary_metrics"]), 4)


        # 2. Test scorecard with ?pipeline_run={older_run.id}
        res_older_card = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/?pipeline_run={self.older_run.id}")
        self.assertEqual(res_older_card.status_code, 200)
        data_older = res_older_card.json()
        self.assertEqual(data_older["paper"]["signal_score"], 45.0)
        self.assertEqual(data_older["paper"]["screening_status"], "borderline")
        self.assertEqual(data_older["paper"]["pipeline_run_id"], str(self.older_run.id))
        self.assertEqual(data_older["metric"]["signal_score"], 45.0)

        # Test component-runs with workspace and pipeline_run filters
        res_cr = self.client.get(f"/api/component-runs/?workspace={self.workspace.id}")
        self.assertEqual(res_cr.status_code, 200)
        cr_items = res_cr.json()
        self.assertEqual(len(cr_items), 1)

        # Test component-runs with pipeline_run=latest
        res_cr_latest = self.client.get(f"/api/component-runs/?workspace={self.workspace.id}&pipeline_run=latest")
        self.assertEqual(res_cr_latest.status_code, 200)
        cr_latest_items = res_cr_latest.json()
        self.assertEqual(len(cr_latest_items), 1)


    def test_6_search_and_frontend_convenience_fields(self):
        """
        Validates full-text search by title/author/doi, as well as published_date
        and pipeline_run_name convenience fields needed for UI screens 3 and 5.
        """
        # Test search matching title fragment
        res = self.client.get(f"/api/papers/?workspace={self.workspace.id}&search=Convolutional")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(self.paper_multi.id))
        self.assertIn("published_date", items[0])
        self.assertIsNotNone(items[0]["published_date"])
        self.assertEqual(items[0]["pipeline_run_name"], "Newer Run 2026-02")

        # Test search matching author
        res_auth = self.client.get(f"/api/papers/?workspace={self.workspace.id}&search=Alice")
        self.assertEqual(res_auth.status_code, 200)
        self.assertEqual(len(res_auth.json()), 1)

        # Test search non-matching
        res_none = self.client.get(f"/api/papers/?workspace={self.workspace.id}&search=NonExistentQuery")
        self.assertEqual(res_none.status_code, 200)
        self.assertEqual(len(res_none.json()), 0)

    def test_7_pipelinerun_domain_and_pagination(self):
        """
        Validates pipeline run filtering by domain (workspace name) and pagination
        with period and total_papers_screened convenience fields for UI screen 6.
        """
        # Filter by domain name
        res = self.client.get("/api/pipeline-runs/?domain=Quantum NLP Contract Workspace")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 2)
        self.assertIn("period", items[0])
        self.assertIn("total_papers_screened", items[0])

        # Test pagination
        res_pag = self.client.get("/api/pipeline-runs/?page=1&page_size=1")
        self.assertEqual(res_pag.status_code, 200)
        pag_data = res_pag.json()
        self.assertIn("count", pag_data)
        self.assertEqual(len(pag_data["results"]), 1)

    def test_8_paper_neighbours_endpoint(self):
        """
        Validates GET /api/papers/{id}/neighbours/ returns lightweight navigation data
        (prev, next, position, total) scoped to workspace and ordered by signal_score desc.
        """
        # Create a second passed paper in the same workspace with lower signal score
        paper_second = Paper.objects.create(
            workspace=self.workspace,
            title="Second Passed Paper in Quantum",
            hash_id="hash_second_passed",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper_second,
            pipeline_run=self.newer_run,
            workspace=self.workspace,
            screening_status="accepted",
            signal_score=60.0
        )

        # 1. First paper (score 88.5) -> position 1 of 2
        res1 = self.client.get(f"/api/papers/{self.paper_multi.id}/neighbours/")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertIsNone(data1["prev"])
        self.assertEqual(data1["next"], str(paper_second.id))
        self.assertEqual(data1["position"], 1)
        self.assertEqual(data1["total"], 2)

        # 2. Second paper (score 60.0) -> position 2 of 2
        res2 = self.client.get(f"/api/papers/{paper_second.id}/neighbours/")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["prev"], str(self.paper_multi.id))
        self.assertIsNone(data2["next"])
        self.assertEqual(data2["position"], 2)
        self.assertEqual(data2["total"], 2)

        # 3. Rejected paper -> position is None, but total is 2
        res_rej = self.client.get(f"/api/papers/{self.paper_older_only.id}/neighbours/")
        self.assertEqual(res_rej.status_code, 200)
        data_rej = res_rej.json()
        self.assertIsNone(data_rej["prev"])
        self.assertIsNone(data_rej["next"])
        self.assertIsNone(data_rej["position"])
        self.assertEqual(data_rej["total"], 2)



