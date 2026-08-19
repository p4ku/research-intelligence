import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from research_intelligence.models import Workspace, WorkspaceMember, APIKey, Scraper
from research_intelligence.mcp.tools import (
    create_workspace_logic,
    list_workspaces_logic,
    get_workspace_logic,
    update_workspace_logic,
    add_workspace_member_logic,
    create_scraper_logic,
    list_scrapers_logic,
    get_scraper_logic,
    update_scraper_logic,
    delete_scraper_logic,
    preview_search_query_logic,
    list_papers_logic,
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    abort_job_logic,
    list_pipeline_runs_logic,
)

User = get_user_model()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class MCPServerTest(TestCase):
    def setUp(self):
        self.patcher = patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
        self.mock_generate = self.patcher.start()
        self.mock_generate.return_value = {
            "passed": True,
            "reasoning": "Mocked LLM generation response",
            "evidence_quotes": ["mock quote"],
            "decision_category": "ACCEPTED"
        }
        self.addCleanup(self.patcher.stop)

        self.admin_user = User.objects.create_user(username="admin_user", email="admin@example.com", password="password123")
        self.researcher_user = User.objects.create_user(username="researcher_user", email="researcher@example.com", password="password123")
        
        # Create API key for admin_user
        self.api_key = APIKey(
            name="Admin Test Key",
            user=self.admin_user,
            scopes=["*"]
        )
        self.raw_secret = self.api_key.generate_key()
        self.api_key.save()

    def test_workspace_crud_and_membership_roles(self):
        # 1. Create Workspace
        res_str = create_workspace_logic(
            user=self.admin_user,
            name="AI Research Workspace",
            abstract_acceptance_criteria="Include papers on Agentic AI",
            ocr_provider="pypdf"
        )
        res = json.loads(res_str)
        self.assertTrue(res["success"])
        ws_id = res["workspace_id"]

        # Verify creator is admin member
        ws = Workspace.objects.get(id=ws_id)
        member = WorkspaceMember.objects.get(workspace=ws, user=self.admin_user)
        self.assertEqual(member.role, "admin")

        # 2. Add researcher member
        add_res_str = add_workspace_member_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            member_username_or_email="researcher@example.com",
            role="researcher"
        )
        add_res = json.loads(add_res_str)
        self.assertTrue(add_res["success"])
        self.assertEqual(add_res["role"], "researcher")

        # 3. List Workspaces for researcher
        ws_list_str = list_workspaces_logic(self.researcher_user)
        ws_list = json.loads(ws_list_str)
        self.assertEqual(len(ws_list), 1)
        self.assertEqual(ws_list[0]["workspace_id"], ws_id)
        self.assertEqual(ws_list[0]["role"], "researcher")

        # 4. Get Workspace details and verify members list
        ws_details_str = get_workspace_logic(self.admin_user, ws_id)
        ws_details = json.loads(ws_details_str)
        self.assertEqual(ws_details["name"], "AI Research Workspace")
        self.assertIn("members", ws_details)
        self.assertEqual(len(ws_details["members"]), 2)
        roles = {m["username"]: m["role"] for m in ws_details["members"]}
        self.assertEqual(roles["admin_user"], "admin")
        self.assertEqual(roles["researcher_user"], "researcher")
        self.assertIn("components_config", ws_details)

    def test_workspace_ocr_provider_default_and_normalization(self):
        # Default ocr_provider should be None
        res_str = create_workspace_logic(
            user=self.admin_user,
            name="Default OCR Workspace"
        )
        res = json.loads(res_str)
        self.assertTrue(res["success"])
        ws_id = res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        self.assertIsNone(ws.ocr_provider)

        # Update ocr_provider to 'pypdf'
        update_workspace_logic(self.admin_user, workspace_id=ws_id, ocr_provider="pypdf")
        ws.refresh_from_db()
        self.assertEqual(ws.ocr_provider, "pypdf")

        # Update ocr_provider with 'none' string -> normalized to None
        update_workspace_logic(self.admin_user, workspace_id=ws_id, ocr_provider="none")
        ws.refresh_from_db()
        self.assertIsNone(ws.ocr_provider)

    def test_scraper_crud(self):
        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Scraper Test Workspace"))
        ws_id = ws_res["workspace_id"]

        # 1. Create Scraper
        create_res = json.loads(create_scraper_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            provider="arxiv",
            search_query="cat:cs.AI AND agentic",
            limit=25,
            sort_by="date",
            sort_order="asc"
        ))
        self.assertTrue(create_res["success"])
        self.assertEqual(create_res["limit"], 25)
        self.assertEqual(create_res["sort_by"], "date")
        self.assertEqual(create_res["sort_order"], "asc")
        scraper_id = create_res["scraper_id"]

        # 2. List Scrapers
        scrapers_list = json.loads(list_scrapers_logic(self.admin_user, ws_id))
        self.assertEqual(len(scrapers_list), 1)
        self.assertEqual(scrapers_list[0]["provider"], "arxiv")
        self.assertEqual(scrapers_list[0]["search_query"], "cat:cs.AI AND agentic")
        self.assertEqual(scrapers_list[0]["limit"], 25)
        self.assertEqual(scrapers_list[0]["sort_by"], "date")
        self.assertEqual(scrapers_list[0]["sort_order"], "asc")

        # 3. Get Scraper
        scraper_details = json.loads(get_scraper_logic(self.admin_user, scraper_id))
        self.assertEqual(scraper_details["provider"], "arxiv")
        self.assertEqual(scraper_details["limit"], 25)
        self.assertEqual(scraper_details["sort_by"], "date")
        self.assertEqual(scraper_details["sort_order"], "asc")

        # 4. Update Scraper
        update_res = json.loads(update_scraper_logic(
            user=self.admin_user,
            scraper_id=scraper_id,
            search_query="cat:cs.AI AND LLM agents",
            limit=15,
            sort_by="relevance",
            sort_order="desc",
            is_active=False
        ))
        self.assertTrue(update_res["success"])
        self.assertFalse(update_res["is_active"])
        self.assertEqual(update_res["limit"], 15)
        self.assertEqual(update_res["sort_by"], "relevance")
        self.assertEqual(update_res["sort_order"], "desc")

        # 5. Delete Scraper
        del_res = json.loads(delete_scraper_logic(self.admin_user, scraper_id))
        self.assertTrue(del_res["success"])
        self.assertEqual(Scraper.objects.filter(id=scraper_id).count(), 0)

    def test_pipeline_run_scraping_job_lifecycle_and_storage(self):
        from django.core.files.storage import default_storage

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Job Storage Workspace"))
        ws_id = ws_res["workspace_id"]

        # Create active scraper
        create_scraper_logic(self.admin_user, ws_id, provider="arxiv", search_query="cat:cs.AI")

        # Mock scraper provider
        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            {
                "hash_id": "2401.00001",
                "source_database": "arxiv",
                "other_url": "https://arxiv.org/abs/2401.00001",
                "title": "Agentic AI Reasoning Engine",
                "authors": "Jane Doe, John Smith",
                "abstract": "An agentic AI approach to automated reviews.",
                "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf"
            }
        ]

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider", return_value=mock_provider):
            trigger_res = json.loads(trigger_search_job_logic(self.admin_user, workspace_id=ws_id, limit=10))
            self.assertTrue(trigger_res["success"])
            pipeline_run_id = trigger_res["pipeline_run_id"]
            component_run_id = trigger_res["component_runs"][0]["component_run_id"]

            # Verify PipelineRun and ComponentRun status
            pr_status = json.loads(get_pipeline_run_status_logic(self.admin_user, pipeline_run_id))
            self.assertEqual(pr_status["status"], "completed")
            self.assertEqual(len(pr_status["component_runs"]), 1)

            sr_status = json.loads(get_component_run_status_logic(self.admin_user, component_run_id))
            self.assertEqual(sr_status["status"], "completed")
            self.assertEqual(sr_status["metrics"]["total_fetched"], 1)
            self.assertEqual(sr_status["metrics"]["total_created"], 1)

            # Verify orthogonal storage file in default_storage
            raw_path = sr_status["raw_storage_path"]
            self.assertTrue(default_storage.exists(raw_path))
            raw_data = json.loads(default_storage.open(raw_path).read().decode('utf-8'))
            self.assertEqual(len(raw_data), 1)
            self.assertEqual(raw_data[0]["title"], "Agentic AI Reasoning Engine")

            # Verify list pipeline runs
            history = json.loads(list_pipeline_runs_logic(self.admin_user, ws_id))
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["pipeline_run_id"], pipeline_run_id)

    def test_pdf_download_job_and_idempotency(self):
        ws_res = json.loads(create_workspace_logic(self.admin_user, "Test Download WS"))
        ws_id = ws_res["workspace_id"]
        scraper_res = json.loads(create_scraper_logic(self.admin_user, ws_id, "arxiv", "cat:cs.AI"))
        scraper_id = scraper_res["scraper_id"]

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            {
                "title": "Agentic AI Reasoning Engine",
                "authors": "Deepmind AI Team",
                "abstract": "We present an autonomous agentic LLM architecture for complex reasoning.",
                "hash_id": "2607.12345",
                "pdf_url": "https://arxiv.org/pdf/2607.12345.pdf",
                "other_url": "http://arxiv.org/abs/2607.12345",
                "source_database": "arxiv",
                "published_date": "2026-07-29T00:00:00Z"
            }
        ]
        mock_provider.download_file.return_value = b"%PDF-1.4 Mock PDF Content Bytes"

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider", return_value=mock_provider), \
             patch("research_intelligence.tasks.step_2_download.fetch.get_scraper_provider", return_value=mock_provider):
            
            # Step 1: Trigger Search Job
            trigger_res = json.loads(trigger_search_job_logic(self.admin_user, workspace_id=ws_id, limit=10))
            pipeline_run_id = trigger_res["pipeline_run_id"]

            # Step 2: Trigger PDF Download Job (First Run)
            dl_res = json.loads(trigger_pdf_download_job_logic(self.admin_user, pipeline_run_id=pipeline_run_id, limit=10))
            self.assertTrue(dl_res["success"])
            dl_comp_id = dl_res["component_run_id"]

            # Check status of PDF download component run
            dl_status = json.loads(get_component_run_status_logic(self.admin_user, dl_comp_id))
            self.assertEqual(dl_status["status"], "completed")
            self.assertEqual(dl_status["metrics"]["downloaded"], 1)
            self.assertEqual(dl_status["metrics"]["skipped"], 0)

            # Step 3: Trigger PDF Download Job again (Idempotency test - no re-downloading!)
            dl_res_2 = json.loads(trigger_pdf_download_job_logic(self.admin_user, pipeline_run_id=pipeline_run_id, limit=10))
            dl_comp_id_2 = dl_res_2["component_run_id"]
            dl_status_2 = json.loads(get_component_run_status_logic(self.admin_user, dl_comp_id_2))
            self.assertEqual(dl_status_2["status"], "completed")
            self.assertEqual(dl_status_2["metrics"]["downloaded"], 0)
            self.assertEqual(dl_status_2["metrics"]["skipped"], 1)

    def test_abort_job(self):
        from research_intelligence.models import PipelineRun, ComponentRun

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Abort Test Workspace"))
        ws_id = ws_res["workspace_id"]
        sc_res = json.loads(create_scraper_logic(self.admin_user, ws_id, provider="openalex", search_query="Agentic AI"))
        scraper_id = sc_res["scraper_id"]

        ws = Workspace.objects.get(id=ws_id)
        scraper = Scraper.objects.get(id=scraper_id)
        pr = PipelineRun.objects.create(workspace=ws, status="running")
        cr = ComponentRun.objects.create(
            pipeline_run=pr,
            step_type='search',
            component_name='openalex_scraper',
            scraper=scraper,
            status="running",
            celery_task_id="mock_celery_task_123"
        )

        # Abort via MCP tool
        abort_res = json.loads(abort_job_logic(self.admin_user, component_run_id=str(cr.id)))
        self.assertTrue(abort_res["success"])

        cr.refresh_from_db()
        self.assertEqual(cr.status, "aborted")

    def test_list_papers_and_optional_params(self):
        from research_intelligence.models import Paper, PipelineRun
        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Paper Listing Test Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        pr = PipelineRun.objects.create(workspace=ws, status="completed")

        # Create Paper record
        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="test_hash_123",
            doi="10.1234/test.doi",
            arxiv_id="2607.99999",
            title="Test Paper on Agentic LLMs",
            authors="Test Author",
            abstract="Full abstract text for testing paper listing without error.",
            source_database="arxiv"
        )

        # 1. Test list_papers_logic (verify no AttributeError and correct fields returned)
        papers_json = list_papers_logic(self.admin_user, workspace_id=ws_id)
        papers = json.loads(papers_json)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Test Paper on Agentic LLMs")
        self.assertEqual(papers[0]["doi"], "10.1234/test.doi")
        self.assertEqual(papers[0]["arxiv_id"], "2607.99999")
        self.assertEqual(papers[0]["abstract"], "Full abstract text for testing paper listing without error.")

        # 2. Test trigger_search_job with scraper_id=None (optional parameter validation test)
        create_scraper_logic(self.admin_user, ws_id, provider="arxiv", search_query="test query")
        with patch('research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay') as mock_delay:
            mock_delay.return_value = MagicMock(id="mock_task_id")
            trigger_res_str = trigger_search_job_logic(self.admin_user, workspace_id=ws_id, scraper_id=None)
            trigger_res = json.loads(trigger_res_str)
            self.assertIn("pipeline_run_id", trigger_res)
            self.assertEqual(len(trigger_res["component_runs"]), 1)

    def test_withdrawn_paper_handling(self):
        from research_intelligence.models import Paper, PipelineRun

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Withdrawn Paper Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        pr = PipelineRun.objects.create(workspace=ws, status="running")

        # Create a paper with screening_status='withdrawn'
        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="withdrawn_hash_999",
            arxiv_id="1905.12288",
            title="Non-real zeros (Withdrawn)",
            authors="J.K. Langley",
            abstract="Paper has been withdrawn by author",
            source_database="arxiv",
            screening_status="withdrawn",
            screening_reasoning="Withdrawn by author"
        )

        dl_res = json.loads(trigger_pdf_download_job_logic(self.admin_user, pipeline_run_id=str(pr.id), limit=10))
        self.assertTrue(dl_res["success"])
        dl_comp_id = dl_res["component_run_id"]

        dl_status = json.loads(get_component_run_status_logic(self.admin_user, dl_comp_id))
        self.assertEqual(dl_status["status"], "completed")
        self.assertEqual(dl_status["metrics"]["withdrawn"], 1)
        self.assertEqual(dl_status["metrics"]["downloaded"], 0)
        self.assertEqual(dl_status["metrics"]["failed"], 0)

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_google_llm_tool(self, mock_generate):
        from research_intelligence.mcp.tools import test_google_llm_logic
        mock_generate.return_value = "Google LLM connectivity test successful with model gemini-3.7-flash."
        res_json = test_google_llm_logic(self.admin_user, prompt="Test prompt", model="gemini-3.7-flash")
        res = json.loads(res_json)
        self.assertTrue(res["success"])
        self.assertEqual(res["requested_model"], "gemini-3.7-flash")
        self.assertIn("Google LLM connectivity test passed", res["message"])

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_screening_output_data_evidence(self, mock_generate):
        from research_intelligence.models import Paper, PipelineRun, ComponentRun
        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job

        mock_generate.return_value = {
            "passed": True,
            "reasoning": "The paper focuses on scalable agentic LLM architecture satisfying acceptance criteria.",
            "evidence_quotes": ["agentic LLM architecture", "scalable distributed reasoning"],
            "decision_category": "ACCEPTED: Core Scope"
        }

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Screening Output Evidence Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        pr = PipelineRun.objects.create(workspace=ws, status="running")

        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="screen_test_123",
            arxiv_id="2401.00001",
            title="Scalable Agentic AI",
            abstract="We present scalable agentic LLM architecture.",
            source_database="arxiv"
        )

        cr = ComponentRun.objects.create(pipeline_run=pr, component_name="abstract_screening", step_type="screening", status="pending")

        execute_screening_job(str(cr.id), limit=10)

        cr.refresh_from_db()
        self.assertEqual(cr.status, "completed")
        self.assertIn("screened_papers", cr.output_data)
        screened_list = cr.output_data["screened_papers"]
        self.assertEqual(len(screened_list), 1)

        p_info = screened_list[0]
        self.assertTrue(p_info["passed"])
        self.assertEqual(p_info["decision_category"], "ACCEPTED: Core Scope")
        self.assertEqual(len(p_info["evidence_quotes"]), 2)
        self.assertIn("agentic LLM architecture", p_info["evidence_quotes"])

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_full_text_screening_job(self, mock_generate):
        from research_intelligence.models import Paper, PipelineRun, ComponentRun
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job

        mock_generate.return_value = {
            "passed": True,
            "reasoning": "The full paper text confirms on-device inference benchmarking satisfying acceptance criteria.",
            "evidence_quotes": ["on-device inference benchmarking", "NPU latency optimization"],
            "decision_category": "ACCEPTED: Full-text validation"
        }

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Full Text Screening Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        pr = PipelineRun.objects.create(workspace=ws, status="running")

        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="full_text_test_999",
            arxiv_id="2401.99999",
            title="On-Device Inference Benchmarking",
            abstract="Abstract of paper...",
            source_database="arxiv"
        )

        cr = ComponentRun.objects.create(pipeline_run=pr, component_name="full_text_screening", step_type="screening", status="pending")

        execute_full_text_screening_job(str(cr.id), limit=10)

        cr.refresh_from_db()
        self.assertEqual(cr.status, "completed")
        self.assertIn("screened_papers", cr.output_data)
        screened_list = cr.output_data["screened_papers"]
        self.assertEqual(len(screened_list), 1)

        p_info = screened_list[0]
        self.assertTrue(p_info["passed"])
        self.assertEqual(p_info["decision_category"], "ACCEPTED: Full-text validation")
        self.assertIn("duration_seconds", p_info)
        self.assertIn("tokens", p_info)

    def test_extraction_definition_crud(self):
        from research_intelligence.mcp.tools import (
            create_extraction_definition_logic,
            list_extraction_definitions_logic,
            get_extraction_definition_logic,
            update_extraction_definition_logic,
            delete_extraction_definition_logic,
        )

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Extraction Def Workspace"))
        ws_id = ws_res["workspace_id"]

        # 1. Create
        create_res = json.loads(create_extraction_definition_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            name="ML Methods",
            system_prompt="Extract all machine learning architectures used.",
            user_prompt_template="Paper text: {paper_text}",
            response_schema={"type": "object", "properties": {"method": {"type": "string"}}},
            llm_model="google/gemini-3.7-flash"
        ))
        self.assertEqual(create_res["status"], "success")
        def_id = create_res["definition_id"]

        # 2. List
        list_res = json.loads(list_extraction_definitions_logic(self.admin_user, ws_id))
        self.assertEqual(len(list_res), 1)
        self.assertEqual(list_res[0]["name"], "ML Methods")

        # 3. Get
        get_res = json.loads(get_extraction_definition_logic(self.admin_user, def_id))
        self.assertEqual(get_res["name"], "ML Methods")
        self.assertIn("response_schema", get_res)

        # 4. Update
        update_res = json.loads(update_extraction_definition_logic(
            user=self.admin_user,
            definition_id=def_id,
            name="Updated ML Methods",
            requires_consensus=True
        ))
        self.assertEqual(update_res["status"], "success")

        # 5. Delete
        delete_res = json.loads(delete_extraction_definition_logic(self.admin_user, def_id))
        self.assertEqual(delete_res["status"], "success")

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_trigger_extraction_job(self, mock_generate):
        from research_intelligence.models import Paper, PipelineRun, ComponentRun, Extraction, ExtractionDefinition
        from research_intelligence.mcp.tools import trigger_extraction_job_logic, create_extraction_definition_logic

        mock_generate.return_value = {
            "fields": {
                "method_name": {
                    "value": "Quantized LLaMA 3.2 3B",
                    "confidence": 0.95,
                    "evidence": [{"quote": "Quantized LLaMA 3.2 3B", "rationale": "Direct mention"}]
                }
            }
        }

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Extraction Job Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        # Create 2 extraction definitions
        create_extraction_definition_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            name="ML Methods",
            system_prompt="Extract ML methods.",
            user_prompt_template="Text: {paper_text}",
            response_schema={"type": "object", "properties": {"method_name": {"type": "string"}}}
        )
        create_extraction_definition_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            name="Hardware Targets",
            system_prompt="Extract hardware targets.",
            user_prompt_template="Text: {paper_text}",
            response_schema={"type": "object", "properties": {"chip": {"type": "string"}}}
        )

        pr = PipelineRun.objects.create(workspace=ws, status="running")
        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="ext_test_101",
            arxiv_id="2401.10101",
            title="Mobile NPU Quantization",
            abstract="Abstract of mobile NPU paper...",
            screening_status="full_text_passed",
            source_database="arxiv"
        )

        trig_res = json.loads(trigger_extraction_job_logic(self.admin_user, pipeline_run_id=str(pr.id), limit=10))
        self.assertTrue(trig_res["success"])
        cr_id = trig_res["component_run_id"]

        cr = ComponentRun.objects.get(id=cr_id)
        self.assertEqual(cr.status, "completed")
        self.assertEqual(cr.step_type, "extraction")
        self.assertIn("extractions", cr.output_data)
        self.assertEqual(len(cr.output_data["extractions"]), 2)
        self.assertIn("total_duration_seconds", cr.output_data)

        # Check Extraction records in DB
        extractions = Extraction.objects.filter(workspace=ws)
        self.assertEqual(extractions.count(), 2)

        # Test list_extractions_logic with pipeline_run_id
        from research_intelligence.mcp.tools import list_extractions_logic, get_paper_extractions_matrix_logic
        list_res = json.loads(list_extractions_logic(self.admin_user, pipeline_run_id=str(pr.id)))
        self.assertEqual(len(list_res), 2)
        self.assertEqual(list_res[0]["paper_id"], str(extractions.first().paper.id))

        # Test get_paper_extractions_matrix_logic
        matrix_res = json.loads(get_paper_extractions_matrix_logic(self.admin_user, pipeline_run_id=str(pr.id), screening_status="full_text_passed"))
        self.assertEqual(matrix_res["total_papers"], 1)
        paper_row = matrix_res["papers"][0]
        self.assertEqual(paper_row["title"], "Mobile NPU Quantization")
        self.assertEqual(paper_row["extractions_count"], 2)
        self.assertIn("ML Methods", paper_row["metrics_summary"])

    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_end_to_end_full_pipeline_success(self, mock_llm_gen, mock_arxiv_search, mock_download_file):
        """
        Tests complete end-to-end execution of all 5 pipeline steps in sequence:
        Step 1 (Search) -> Step 2 (PDF Download) -> Step 4 (Abstract Screening) -> Step 4b (Full Text Screening) -> Step 5 (Extraction).
        Verifies lifecycle states, component run metrics, token accumulation, and pipeline completion.
        """
        mock_download_file.return_value = b"%PDF-1.4 Mock PDF Binary Content for Testing"
        from research_intelligence.models import Paper, PipelineRun, ComponentRun, Extraction
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
        from research_intelligence.mcp.tools import (
            create_workspace_logic,
            create_scraper_logic,
            create_extraction_definition_logic,
            trigger_search_job_logic,
            trigger_pdf_download_job_logic,
            trigger_screening_job_logic,
            trigger_extraction_job_logic,
            get_pipeline_run_status_logic
        )

        # 1. Setup Workspace, Scraper, and Extraction Definition
        ws_res = json.loads(create_workspace_logic(self.admin_user, name="End-to-End Pipeline Workspace"))
        ws_id = ws_res["workspace_id"]

        create_scraper_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            provider="arxiv",
            search_query="cat:cs.AI AND Small Language Models"
        )

        create_extraction_definition_logic(
            user=self.admin_user,
            workspace_id=ws_id,
            name="Model Parameters",
            system_prompt="Extract model parameter count.",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object", "properties": {"params": {"type": "string"}}}
        )

        # Mock Step 1 Arxiv response
        mock_arxiv_search.return_value = [
            {
                "hash_id": "2401.55555",
                "title": "Scalable On-Device SLM Benchmarks",
                "authors": "Jane Doe, John Smith",
                "abstract": "We present benchmark results for Small Language Models on mobile NPUs.",
                "doi": "10.1145/3333333.4444444",
                "arxiv_id": "2401.55555",
                "pdf_url": "https://arxiv.org/pdf/2401.55555.pdf",
                "other_url": "https://arxiv.org/abs/2401.55555",
                "source_database": "arxiv",
                "published_date": "2026-01-15T00:00:00Z",
                "is_withdrawn": False,
                "withdrawn_reason": ""
            }
        ]

        # Mock Step 2 PDF HTTP download handled by mock_download_file
        mock_download_file.return_value = b"%PDF-1.4 Mock PDF Binary Content for Testing"

        # Mock Step 4 / 5 LLM responses
        mock_llm_gen.return_value = {
            "passed": True,
            "reasoning": "Direct match for small language models and mobile NPU efficiency.",
            "evidence_quotes": ["Small Language Models", "mobile NPUs"],
            "decision_category": "ACCEPTED: Core Scope",
            "fields": {
                "params": {
                    "value": "3 Billion",
                    "confidence": 0.98,
                    "evidence": [{"quote": "3 Billion parameters", "rationale": "Direct mention"}]
                }
            }
        }

        # --- STEP 1: Search ---
        search_res = json.loads(trigger_search_job_logic(self.admin_user, workspace_id=ws_id, limit=5))
        self.assertTrue(search_res["success"])
        pr_id = search_res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.total_papers_fetched, 1)

        # --- STEP 2: PDF Download ---
        dl_res = json.loads(trigger_pdf_download_job_logic(self.admin_user, pipeline_run_id=pr_id, limit=5))
        self.assertTrue(dl_res["success"])

        # --- STEP 4: Abstract Screening ---
        scr_res = json.loads(trigger_screening_job_logic(self.admin_user, pipeline_run_id=pr_id, limit=5))
        self.assertTrue(scr_res["success"])

        # --- STEP 4b: Full-Text Screening ---
        cr_ft = ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="full_text_screening", status="pending")
        ft_success = execute_full_text_screening_job(str(cr_ft.id), limit=5)
        self.assertTrue(ft_success)

        # --- STEP 5: Parameter Extraction ---
        ext_res = json.loads(trigger_extraction_job_logic(self.admin_user, pipeline_run_id=pr_id, limit=5))
        self.assertTrue(ext_res["success"])

        # Verify complete pipeline status and component runs
        pr.refresh_from_db()
        self.assertEqual(pr.status, "completed")

        component_runs = ComponentRun.objects.filter(pipeline_run=pr)
        self.assertEqual(component_runs.count(), 5)
        for cr in component_runs:
            self.assertEqual(cr.status, "completed")
            if cr.step_type in ["screening", "extraction"]:
                self.assertIn("total_duration_seconds", cr.output_data)

        # Verify extractions saved
        extractions = Extraction.objects.filter(workspace__id=ws_id)
        self.assertEqual(extractions.count(), 1)

        # Check full status payload logic
        status_payload = json.loads(get_pipeline_run_status_logic(self.admin_user, pr_id))
        self.assertEqual(status_payload["status"], "completed")
        self.assertEqual(status_payload["downloaded_documents_count"], 1)
        self.assertIn("storage", status_payload)
        self.assertIn("size_bytes", status_payload["storage"])
        self.assertIn("size_formatted", status_payload["storage"])
        self.assertIn("total_files", status_payload["storage"])

    def test_end_to_end_pipeline_failures(self):
        """
        Tests pipeline failure modes and recovery handling:
        1. ComponentRun failure when task encounters unhandled exception.
        2. Aborting a running job via abort_job_logic.
        """
        from research_intelligence.models import Paper, PipelineRun, ComponentRun
        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
        from research_intelligence.mcp.tools import create_workspace_logic, abort_job_logic

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Failure Mode Test Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        pr = PipelineRun.objects.create(workspace=ws, status="running")
        Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="fail_test_001",
            title="Paper for Failure Testing",
            abstract="Abstract content...",
            source_database="arxiv"
        )

        cr_fail = ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="abstract_screening", status="pending")

        # 1. Simulate unhandled exception during execute_screening_job
        with patch("research_intelligence.models.Paper.objects.filter", side_effect=RuntimeError("Database Connection Lost")):
            res = execute_screening_job(str(cr_fail.id), limit=5)
            self.assertFalse(res)

        cr_fail.refresh_from_db()
        self.assertEqual(cr_fail.status, "failed")
        self.assertIn("Database Connection Lost", cr_fail.error_message)

        pr.refresh_from_db()
        self.assertEqual(pr.status, "failed")

        # 2. Test Aborting a job cleanly
        pr2 = PipelineRun.objects.create(workspace=ws, status="running")
        cr_abort = ComponentRun.objects.create(pipeline_run=pr2, step_type="download", component_name="pdf_downloader", status="running")

        abort_res = json.loads(abort_job_logic(self.admin_user, component_run_id=str(cr_abort.id)))
        self.assertTrue(abort_res["success"])

        cr_abort.refresh_from_db()
        self.assertEqual(cr_abort.status, "aborted")

    def test_google_llm_resource_exhausted_retry_backoff(self):
        """
        Tests automatic retry strategy with exponential backoff when Google GenAI raises
        429 RESOURCE_EXHAUSTED errors.
        """
        from research_intelligence.llm_providers.google import GoogleAgentAPIProvider

        provider = GoogleAgentAPIProvider(api_key="mock_key")
        mock_client = MagicMock()

        mock_success_response = MagicMock()
        mock_success_response.text = "Success after retry"
        mock_success_response.parsed = None
        mock_success_response.usage_metadata = None

        # Simulate 429 RESOURCE_EXHAUSTED on first 2 calls, then success on 3rd call
        mock_client.models.generate_content.side_effect = [
            RuntimeError("429 RESOURCE_EXHAUSTED. Resource exhausted. Please try again later."),
            RuntimeError("429 RESOURCE_EXHAUSTED. Resource exhausted. Please try again later."),
            mock_success_response
        ]

        with patch.object(provider, "_get_client", return_value=mock_client), patch("research_intelligence.llm_providers.google.time.sleep") as mock_sleep:
            self.patcher.stop()
            try:
                res = provider.generate(prompt="Test prompt", max_retries=5)
            finally:
                self.patcher.start()
            self.assertEqual(res, "Success after retry")
            self.assertEqual(mock_client.models.generate_content.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)

    def test_list_and_get_extractions_mcp_tools(self):
        """
        Tests MCP tools for browsing Step 5 Extraction objects:
        1. list_extractions_logic
        2. get_extraction_logic
        """
        from research_intelligence.models import Paper, Extraction, ExtractionDefinition, PipelineRun
        from research_intelligence.mcp.tools import list_extractions_logic, get_extraction_logic, create_workspace_logic

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Extraction Browse Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        pr = PipelineRun.objects.create(workspace=ws, status="running")
        paper = Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="ext_browse_001",
            title="Quantization for Mobile NPUs",
            source_database="arxiv"
        )

        ext_def = ExtractionDefinition.objects.create(
            workspace=ws,
            name="TRL Assessment",
            system_prompt="Assess TRL level.",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object"}
        )

        ext = Extraction.objects.create(
            workspace=ws,
            paper=paper,
            extraction_definition=ext_def,
            category="TRL Assessment",
            fields_data={"trl_level": 3, "trl_name": "Proof of Concept"},
            validation_status="pass",
            confidence_score=0.95
        )

        # 1. Test list_extractions_logic
        list_res = json.loads(list_extractions_logic(self.admin_user, workspace_id=ws_id))
        self.assertEqual(len(list_res), 1)
        self.assertEqual(list_res[0]["id"], str(ext.id))
        self.assertEqual(list_res[0]["fields_data"]["trl_level"], 3)

        # 2. Test get_extraction_logic
        get_res = json.loads(get_extraction_logic(self.admin_user, str(ext.id)))
        self.assertEqual(get_res["id"], str(ext.id))
        self.assertEqual(get_res["paper_title"], "Quantization for Mobile NPUs")
        self.assertEqual(get_res["system_prompt"], "Assess TRL level.")

    def test_delete_pipeline_run_mcp_tool(self):
        """
        Tests delete_pipeline_run_logic MCP tool deleting a PipelineRun,
        associated Papers, Extractions, ComponentRuns, and physical files from storage.
        """
        from research_intelligence.models import Paper, Extraction, ExtractionDefinition, PipelineRun, ComponentRun
        from research_intelligence.mcp.tools import delete_pipeline_run_logic, create_workspace_logic
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Delete Pipeline Workspace"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        pr = PipelineRun.objects.create(workspace=ws, status="completed")
        comp = ComponentRun.objects.create(pipeline_run=pr, step_type="search", component_name="arxiv", status="completed")

        pdf_path = default_storage.save(f"workspaces/{ws.id}/runs/{pr.id}/documents/hash123/original.pdf", ContentFile(b"%PDF-mock"))
        md_path = default_storage.save(f"workspaces/{ws.id}/runs/{pr.id}/documents/hash123/ocr.md", ContentFile(b"# OCR text"))
        meta_path = default_storage.save(f"workspaces/{ws.id}/runs/{pr.id}/documents/hash123/metadata.json", ContentFile(b"{}"))
        raw_scrape_path = default_storage.save(f"workspaces/{ws.id}/runs/{pr.id}/scrapes/arxiv/{comp.id}_raw.json", ContentFile(b"[]"))

        paper = Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="del_hash_001",
            title="Paper to be deleted",
            source_database="arxiv",
            original_pdf_path=pdf_path,
            converted_md_path=md_path
        )

        ext_def = ExtractionDefinition.objects.create(
            workspace=ws,
            name="Delete Definition",
            system_prompt="System prompt",
            user_prompt_template="User template",
            response_schema={}
        )

        ext = Extraction.objects.create(
            workspace=ws,
            paper=paper,
            extraction_definition=ext_def,
            category="Test",
            fields_data={"test": "data"}
        )

        # Assert items exist before deletion
        self.assertTrue(default_storage.exists(pdf_path))
        self.assertTrue(default_storage.exists(md_path))
        self.assertTrue(default_storage.exists(meta_path))
        self.assertTrue(default_storage.exists(raw_scrape_path))
        self.assertTrue(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertTrue(Paper.objects.filter(id=paper.id).exists())
        self.assertTrue(Extraction.objects.filter(id=ext.id).exists())

        # Call delete_pipeline_run_logic
        del_res = json.loads(delete_pipeline_run_logic(self.admin_user, str(pr.id)))
        self.assertEqual(del_res["status"], "success")
        self.assertEqual(del_res["deleted_counts"]["papers"], 1)
        self.assertEqual(del_res["deleted_counts"]["extractions"], 1)
        self.assertEqual(del_res["deleted_counts"]["storage_files"], 4)

        # Assert items and entire run directory are completely deleted after calling delete_pipeline_run_logic
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertFalse(ComponentRun.objects.filter(id=comp.id).exists())
        self.assertFalse(Paper.objects.filter(id=paper.id).exists())
        self.assertFalse(Extraction.objects.filter(id=ext.id).exists())
        self.assertFalse(default_storage.exists(pdf_path))
        self.assertFalse(default_storage.exists(md_path))
        self.assertFalse(default_storage.exists(meta_path))
        self.assertFalse(default_storage.exists(raw_scrape_path))
        self.assertFalse(default_storage.exists(f"workspaces/{ws.id}/runs/{pr.id}"))

    def test_trigger_ocr_job_mcp_tool(self):
        """
        Tests trigger_ocr_job_logic FastMCP tool creating ComponentRun and parsing paper PDF into Markdown text.
        """
        from research_intelligence.models import Paper, PipelineRun
        from research_intelligence.mcp.tools import trigger_ocr_job_logic, create_workspace_logic
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        ws_res = json.loads(create_workspace_logic(self.admin_user, name="OCR Test Workspace", ocr_provider="pypdf"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        pr = PipelineRun.objects.create(workspace=ws, status="running")
        pdf_path = default_storage.save(f"workspaces/{ws.id}/runs/{pr.id}/documents/ocr_hash1/original.pdf", ContentFile(b"%PDF-1.4 Mock Paper Content"))

        paper = Paper.objects.create(
            workspace=ws,
            pipeline_run=pr,
            hash_id="ocr_hash1",
            title="Deep Residual Learning for Image Recognition",
            source_database="arxiv",
            original_pdf_path=pdf_path
        )

        with patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider") as mock_ocr:
            mock_provider_inst = MagicMock()
            mock_provider_inst.convert.return_value = "# Deep Residual Learning\n\nAbstract\nDeeper neural networks are more difficult to train..."
            mock_ocr.return_value = mock_provider_inst

            ocr_res = json.loads(trigger_ocr_job_logic(self.admin_user, pipeline_run_id=str(pr.id)))
            self.assertTrue(ocr_res["success"])
            self.assertEqual(ocr_res["ocr_provider"], "pypdf")

        paper.refresh_from_db()
        self.assertIsNotNone(paper.converted_md_path)
        self.assertTrue(default_storage.exists(paper.converted_md_path))

    def test_workspace_token_and_cost_recording(self):
        """
        Verifies that workspace records split input/output tokens and calculates USD cost.
        """
        from research_intelligence.mcp.tools import create_workspace_logic, get_workspace_logic, list_workspaces_logic
        ws_res = json.loads(create_workspace_logic(self.admin_user, name="Token Metric Test WS"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        self.assertEqual(ws.tokens_in_consumed_this_month, 0)
        self.assertEqual(ws.tokens_out_consumed_this_month, 0)
        self.assertEqual(ws.tokens_consumed_this_month, 0)

        # Record token usage
        cost = ws.record_token_usage(tokens_in=7219, tokens_out=2910, model_name="google/gemini-3.7-flash")
        self.assertGreater(cost, 0)

        ws.refresh_from_db()
        self.assertEqual(ws.tokens_in_consumed_this_month, 7219)
        self.assertEqual(ws.tokens_out_consumed_this_month, 2910)
        self.assertEqual(ws.tokens_consumed_this_month, 10129)
        self.assertGreater(ws.usd_spent_this_month, 0)

        # Verify get_workspace_logic includes split token metrics
        details = json.loads(get_workspace_logic(self.admin_user, ws_id))
        self.assertEqual(details["components_config"]["tokens_in_consumed_this_month"], 7219)
        self.assertEqual(details["components_config"]["tokens_out_consumed_this_month"], 2910)
        self.assertEqual(details["components_config"]["tokens_consumed_this_month"], 10129)
        self.assertGreater(details["components_config"]["usd_spent_this_month"], 0)

        # Verify list_workspaces_logic includes split token metrics
        ws_list = json.loads(list_workspaces_logic(self.admin_user))
        matched = [w for w in ws_list if w["workspace_id"] == ws_id][0]
        self.assertEqual(matched["tokens_in_consumed_this_month"], 7219)
        self.assertEqual(matched["tokens_out_consumed_this_month"], 2910)
        self.assertEqual(matched["tokens_consumed_this_month"], 10129)

