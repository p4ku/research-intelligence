from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, Paper, ExtractionDefinition, Extraction, PipelineRun
from research_intelligence.admin import ExtractionAdmin

User = get_user_model()


class ExtractionExitMetricTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="metric_tester", email="test@example.com", password="pass")
        self.workspace = Workspace.objects.create(name="Exit Metric Workspace")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_123",
            title="Hybrid Quantum-Classical Neural Architectures",
            authors="Alice et al.",
            abstract="Sample abstract",
            source_database="arxiv"
        )
        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            exit_metric="fit_score",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.admin = ExtractionAdmin(Extraction, AdminSite())

    def test_fit_score_exit_metric_unpacking(self):
        # When definition has exit_metric="fit_score", it unpacks "14" directly
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.ext_def,
            category="Schwarz Fit",
            fields_data={"fit_score": 14, "rationale": "High business impact for cloud computing"}
        )
        self.assertEqual(ext.exit_metric, "14")
        self.assertEqual(ext.get_exit_metric(), "14")
        badge_html = self.admin.exit_metric_badge(ext)
        self.assertIn("14", badge_html)

    def test_nested_value_exit_metric_unpacking(self):
        trl_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Assessment",
            exit_metric="trl_score",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=trl_def,
            category="TRL Assessment",
            fields_data={"trl_score": {"value": 6, "confidence": 0.9}, "evidence": "Tested in lab"}
        )
        self.assertEqual(ext.exit_metric, "6")
        self.assertEqual(ext.get_exit_metric(), "6")

    def test_dynamic_update_when_definition_changes(self):
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.ext_def,
            category="Schwarz Fit",
            fields_data={"fit_score": 14, "custom_score": 99}
        )
        self.assertEqual(ext.exit_metric, "14")
        # Change definition key dynamically without updating Extraction row
        self.ext_def.exit_metric = "custom_score"
        self.ext_def.save()
        self.assertEqual(ext.exit_metric, "99")

    def test_empty_fields_data(self):
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.ext_def,
            category="Empty",
            fields_data={}
        )
        self.assertEqual(ext.get_exit_metric(), "-")
        self.assertIn("-", str(self.admin.exit_metric_badge(ext)))
