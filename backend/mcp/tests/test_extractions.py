import json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember, Paper, Extraction, ExtractionDefinition, PipelineRun
from mcp.tools import (
    create_extraction_definition_logic,
    list_extraction_definitions_logic,
    get_extraction_definition_logic,
    update_extraction_definition_logic,
    delete_extraction_definition_logic,
    list_extractions_logic,
    get_paper_extractions_matrix_logic,
    get_extraction_logic,
    trigger_extraction_job_logic,
)

User = get_user_model()


class MCPExtractionsTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="ext_admin", email="admin@schwarz.de", password="password")
        self.workspace = Workspace.objects.create(name="Extraction Test WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")

    def test_extraction_definition_crud(self):
        res_str = create_extraction_definition_logic(
            self.admin_user,
            workspace_id=str(self.workspace.id),
            name="TRL Level",
            exit_metric="trl_score",
            system_prompt="Extract technology readiness level between 1-9",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}}
        )
        res = json.loads(res_str)
        self.assertEqual(res["status"], "success")
        d_id = res["definition_id"]

        defs = json.loads(list_extraction_definitions_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["name"], "TRL Level")

        up_res = json.loads(update_extraction_definition_logic(self.admin_user, definition_id=d_id, system_prompt="Updated prompt"))
        self.assertEqual(up_res["status"], "success")

        del_res = json.loads(delete_extraction_definition_logic(self.admin_user, definition_id=d_id))
        self.assertEqual(del_res["status"], "success")
        self.assertEqual(ExtractionDefinition.objects.filter(workspace=self.workspace).count(), 0)

    def test_list_and_get_extractions_mcp_tools(self):
        run = PipelineRun.objects.create(workspace=self.workspace)
        p = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_ext_p1",
            title="Extraction Target Paper",
            abstract="Target abstract",
            screening_status="full_text_passed"
        )

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

        list_res = json.loads(list_extractions_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(list_res), 1)

        matrix_res = json.loads(get_paper_extractions_matrix_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(matrix_res["papers"]), 1)

        get_res = json.loads(get_extraction_logic(self.admin_user, extraction_id=str(ext.id)))
        self.assertEqual(get_res["extraction_id"], str(ext.id))
        self.assertEqual(get_res["fields_data"]["novelty"], 9.5)
