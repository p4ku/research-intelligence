from research_intelligence.models import Paper, PaperMetric, Extraction, ExtractionDefinition, PipelineRun
from mcp_server.tools import (
    create_extraction_definition_logic,
    get_extraction_definition_logic,
    list_extraction_definitions_logic,
    update_extraction_definition_logic,
    delete_extraction_definition_logic,
    list_extractions_logic,
    get_paper_extractions_matrix_logic,
    get_extraction_logic,
)
from .base import BaseMCPTestCase


class MCPExtractionsTestCase(BaseMCPTestCase):
    def test_extraction_definition_crud(self):
        res = self.parse_res(create_extraction_definition_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            name="TRL Level",
            exit_metric="trl_score",
            system_prompt="Extract technology readiness level between 1-9",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}}
        ))
        self.assertEqual(res["status"], "success")
        d_id = res["definition_id"]

        defs = self.parse_res(list_extraction_definitions_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["name"], "TRL Level")

        up_res = self.parse_res(update_extraction_definition_logic(self.admin, definition_id=d_id, system_prompt="Updated prompt"))
        self.assertEqual(up_res["status"], "success")

        del_res = self.parse_res(delete_extraction_definition_logic(self.admin, definition_id=d_id))
        self.assertEqual(del_res["status"], "success")
        self.assertEqual(ExtractionDefinition.objects.filter(workspace=self.workspace).count(), 0)

    def test_extraction_definition_postprocessing_crud(self):
        # 1. Create with postprocessing_code
        res = self.parse_res(create_extraction_definition_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            name="Fit Definition",
            exit_metric="fit_score",
            system_prompt="Extract fit score",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object"},
            postprocessing_code="return fit_score * 2.5"
        ))
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["has_postprocessing_code"])
        d_id = res["definition_id"]

        # 2. Get detailed view
        details = self.parse_res(get_extraction_definition_logic(self.admin, definition_id=d_id))
        self.assertEqual(details["postprocessing_code"], "return fit_score * 2.5")

        # 3. List
        defs = self.parse_res(list_extraction_definitions_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(defs), 1)
        self.assertTrue(defs[0]["has_postprocessing_code"])

        # 4. Update postprocessing_code
        up_res = self.parse_res(update_extraction_definition_logic(
            self.admin,
            definition_id=d_id,
            postprocessing_code="return fit_score * 3.0"
        ))
        self.assertEqual(up_res["status"], "success")
        self.assertIn("postprocessing_code", up_res["updated_fields"])

        details_updated = self.parse_res(get_extraction_definition_logic(self.admin, definition_id=d_id))
        self.assertEqual(details_updated["postprocessing_code"], "return fit_score * 3.0")

        delete_extraction_definition_logic(self.admin, definition_id=d_id)

    def test_extraction_definition_exit_metrics_list_and_postprocessing_manipulation(self):
        """
        Verify MCP tools support creating and updating extraction definitions
        with an explicit list of exit parameters (exit_metrics: list[str]) and Python postprocessing snippets.
        """
        # 1. Create with exit_metrics as a list of strings
        res = self.parse_res(create_extraction_definition_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            name="Multi Metric Target",
            exit_metrics=["market_fit", "growth_potential", "risk_factor"],
            system_prompt="Extract market metrics",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object"},
            postprocessing_code="return (market_fit * 2.0) + growth_potential - risk_factor"
        ))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["exit_metric"], "market_fit, growth_potential, risk_factor")
        self.assertEqual(res["exit_metrics"], ["market_fit", "growth_potential", "risk_factor"])
        self.assertTrue(res["has_postprocessing_code"])
        d_id = res["definition_id"]

        # 2. Get details and inspect exit_metrics list + postprocessing_code
        details = self.parse_res(get_extraction_definition_logic(self.admin, definition_id=d_id))
        self.assertEqual(details["exit_metric"], "market_fit, growth_potential, risk_factor")
        self.assertEqual(details["exit_metrics"], ["market_fit", "growth_potential", "risk_factor"])
        self.assertEqual(details["postprocessing_code"], "return (market_fit * 2.0) + growth_potential - risk_factor")

        # 3. List definitions
        defs = self.parse_res(list_extraction_definitions_logic(self.admin, workspace_id=str(self.workspace.id)))
        found = next(d for d in defs if d["definition_id"] == d_id)
        self.assertEqual(found["exit_metrics"], ["market_fit", "growth_potential", "risk_factor"])
        self.assertTrue(found["has_postprocessing_code"])

        # 4. Update exit_metrics with a new list and update postprocessing snippet
        up_res = self.parse_res(update_extraction_definition_logic(
            self.admin,
            definition_id=d_id,
            exit_metrics=["market_fit", "roi_ratio"],
            postprocessing_code="return market_fit * roi_ratio"
        ))
        self.assertEqual(up_res["status"], "success")
        self.assertEqual(up_res["exit_metrics"], ["market_fit", "roi_ratio"])
        self.assertEqual(up_res["postprocessing_code"], "return market_fit * roi_ratio")

        # 5. Verify invalid syntax handling
        err_res = update_extraction_definition_logic(
            self.admin,
            definition_id=d_id,
            postprocessing_code="def broken_syntax(:"
        )
        self.assertIn("Invalid Python syntax", err_res)

        # 6. Clean up
        delete_extraction_definition_logic(self.admin, definition_id=d_id)

    def test_list_and_get_extractions_mcp_tools(self):
        run = PipelineRun.objects.create(workspace=self.workspace)
        p = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_ext_p1",
            title="Extraction Target Paper",
            abstract="Target abstract"
        )
        PaperMetric.objects.create(paper=p, pipeline_run=run, workspace=self.workspace, screening_status="full_text_passed")

        defn = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            system_prompt="Extract novelty",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=p,
            extraction_definition=defn,
            fields_data={"novelty": 9.5},
            confidence_score=0.98,
            validation_status="pass"
        )

        list_res = self.parse_res(list_extractions_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(list_res), 1)

        matrix_res = self.parse_res(get_paper_extractions_matrix_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(matrix_res["papers"]), 1)

        get_res = self.parse_res(get_extraction_logic(self.admin, extraction_id=str(ext.id)))
        self.assertEqual(get_res["extraction_id"], str(ext.id))
        self.assertEqual(get_res["fields_data"]["novelty"], 9.5)

    def test_matrix_filtering_resilience(self):
        run = PipelineRun.objects.create(workspace=self.workspace)
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p1_abs",
            title="Abstract Passed Paper"
        )
        PaperMetric.objects.create(paper=p1, pipeline_run=run, workspace=self.workspace, screening_status="abstract_passed")
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p2_ft",
            title="Full-Text Passed Paper"
        )
        PaperMetric.objects.create(paper=p2, pipeline_run=run, workspace=self.workspace, screening_status="full_text_passed")
        p3 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p3_acc",
            title="Accepted Paper"
        )
        PaperMetric.objects.create(paper=p3, pipeline_run=run, workspace=self.workspace, screening_status="accepted")
        p4 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p4_rej",
            title="Rejected Paper"
        )
        PaperMetric.objects.create(paper=p4, pipeline_run=run, workspace=self.workspace, screening_status="rejected")

        # Default filter ("full_text_passed") includes abstract_passed, full_text_passed, accepted (3 papers)
        matrix_res = self.parse_res(get_paper_extractions_matrix_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(matrix_res["total_papers"], 3)
        paper_ids = [p["paper_id"] for p in matrix_res["papers"]]
        self.assertIn(str(p1.id), paper_ids)
        self.assertIn(str(p2.id), paper_ids)
        self.assertIn(str(p3.id), paper_ids)
        self.assertNotIn(str(p4.id), paper_ids)

    def test_extraction_tenant_isolation_unauthorized_access(self):
        from django.contrib.auth import get_user_model
        from research_intelligence.models import Workspace, WorkspaceMember
        User = get_user_model()

        other_user = User.objects.create_user(username="stranger_user", password="password123")
        other_ws = Workspace.objects.create(name="Foreign Workspace")
        WorkspaceMember.objects.create(workspace=other_ws, user=other_user, role="admin")

        foreign_run = PipelineRun.objects.create(workspace=other_ws)
        foreign_p = Paper.objects.create(workspace=other_ws, pipeline_run=foreign_run, hash_id="foreign_p_01", title="Foreign Paper")
        foreign_ext = Extraction.objects.create(
            workspace=other_ws,
            paper=foreign_p,
            category="confidential",
            fields_data={"classified": True}
        )

        # 1. User cannot access foreign extraction directly
        res_ext = self.parse_res(get_extraction_logic(self.researcher, extraction_id=str(foreign_ext.id)))
        self.assertIn("error", res_ext)

        # 2. User querying list_extractions with foreign workspace_id gets error
        res_list = self.parse_res(list_extractions_logic(self.researcher, workspace_id=str(other_ws.id)))
        self.assertIn("error", res_list)


