import json
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    Extraction,
    ExtractionDefinition,
    ResearchAgentProcess,
    Scraper,
)
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

User = get_user_model()


class PipelineTestHarness:
    """
    Modular testing harness and simulation abstraction for Schwarz Research Intelligence pipelines.
    Enables parameterized testing across any combination of:
    - OCR Engine (None / Direct Multimodal PDF vs pypdf vs Mistral)
    - Screening Workflow (2-Stage Abstract+FullText vs Direct Full-Text only)
    - Dynamic Extraction Schemas & Rules
    - Controlled mid-pipeline failure injection (Search 404/Timeout, 429 Rate Limits, Zero-Passes)
    """

    def __init__(self, name: str = "Test Pipeline Lab", username: str = "pipeline_lead"):
        self.user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@company.com", "password": "password123"}
        )
        self.workspace = None
        self.pipeline_run = None
        self.agent_process = None
        self.scrapers = []
        self.extraction_definitions = []
        self.papers = []
        self.name = name

    def configure_workspace(
        self,
        ocr_provider: str | None = None,
        skip_abstract_screening: bool = False,
        screening_llm_model: str = "google/gemini-3.7-flash",
        llm_provider: str = "google",
        abstract_acceptance: str = "Accept relevant research.",
        abstract_rejection: str = "Reject non-relevant.",
        full_text_acceptance: str = "Accept validated methodology.",
        full_text_rejection: str = "Reject flawed methodology.",
    ) -> "PipelineTestHarness":
        """Configures a fresh isolated workspace with custom screening criteria and OCR engine."""
        self.workspace = Workspace.objects.create(
            name=self.name,
            ocr_provider=ocr_provider,
            skip_abstract_screening=skip_abstract_screening,
            screening_llm_model=screening_llm_model,
            llm_provider=llm_provider,
            abstract_acceptance_criteria=abstract_acceptance,
            abstract_rejection_criteria=abstract_rejection,
            full_text_acceptance_criteria=full_text_acceptance,
            full_text_rejection_criteria=full_text_rejection,
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        return self

    def add_scraper(self, provider: str = "arxiv", search_query: str = "quantum machine learning") -> "PipelineTestHarness":
        """Adds an active scraper configuration to the workspace."""
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider=provider,
            search_query=search_query,
            is_active=True
        )
        self.scrapers.append(scraper)
        return self

    def add_extraction_definition(
        self,
        name: str = "Extracted Targets",
        exit_metric: str | None = None,
        response_schema: dict | None = None
    ) -> "PipelineTestHarness":
        """Adds a dynamic parameter extraction target to the workspace."""
        schema = response_schema or {"type": "object", "properties": {"result": {"type": "string"}}}
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name=name,
            exit_metric=exit_metric,
            llm_model=self.workspace.screening_llm_model,
            system_prompt=f"Extract parameters for {name}.",
            response_schema=schema,
            is_active=True
        )
        self.extraction_definitions.append(definition)
        return self

    def _tick(self):
        """Executes tick_agent_process with Celery async task dispatchers safely mocked."""
        with patch("research_intelligence.tasks.step_1_search.search.execute_workspace_search.delay") as m_s_d, \
             patch("research_intelligence.tasks.step_1_search.search.execute_workspace_search.apply_async") as m_s_a, \
             patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay") as m_sr_d, \
             patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.apply_async") as m_sr_a, \
             patch("research_intelligence.tasks.step_2_download.fetch.execute_pdf_download_job.delay") as m_dl_d, \
             patch("research_intelligence.tasks.step_2_download.fetch.execute_pdf_download_job.apply_async") as m_dl_a, \
             patch("research_intelligence.tasks.step_3_ocr.convert.execute_ocr_job.delay") as m_ocr_d, \
             patch("research_intelligence.tasks.step_3_ocr.convert.execute_ocr_job.apply_async") as m_ocr_a, \
             patch("research_intelligence.tasks.step_4_screening.abstract.execute_screening_job.delay") as m_abs_d, \
             patch("research_intelligence.tasks.step_4_screening.abstract.execute_screening_job.apply_async") as m_abs_a, \
             patch("research_intelligence.tasks.step_4_screening.full_text.execute_full_text_screening_job.delay") as m_ft_d, \
             patch("research_intelligence.tasks.step_4_screening.full_text.execute_full_text_screening_job.apply_async") as m_ft_a, \
             patch("research_intelligence.tasks.step_5_extraction.extract.execute_extraction_job.delay") as m_ext_d, \
             patch("research_intelligence.tasks.step_5_extraction.extract.execute_extraction_job.apply_async") as m_ext_a, \
             patch("research_intelligence.tasks.orchestrator.agent_engine.run_agent_process_tick.delay") as m_tick_d, \
             patch("research_intelligence.tasks.orchestrator.agent_engine.run_agent_process_tick.apply_async") as m_tick_a, \
             patch("research_intelligence.tasks.orchestrator.agent_engine._send_agent_notification"):
            
            for m in [m_s_d, m_s_a, m_sr_d, m_sr_a, m_dl_d, m_dl_a, m_ocr_d, m_ocr_a, m_abs_d, m_abs_a, m_ft_d, m_ft_a, m_ext_d, m_ext_a, m_tick_d, m_tick_a]:
                m.return_value.id = "mock_task_id"
            
            res = tick_agent_process(str(self.agent_process.id))
            return res

    def start_agent(self, name: str = "Simulated Agent") -> "PipelineTestHarness":
        """Initializes and kicks off the agent state machine."""
        self.agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            name=name,
            status="pending",
            current_step="initialized"
        )
        # First tick transitions initialized -> search
        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run = self.agent_process.pipeline_run
        return self

    def complete_step_1_search(self, papers_data: list[dict]) -> "PipelineTestHarness":
        """Simulates completing Step 1 (Search & Ingestion) with given paper items."""
        search_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='search')
        for run in search_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'total_created': len(papers_data), 'total_duplicates_skipped': 0}
            run.save()

        for idx, item in enumerate(papers_data, 1):
            hash_id = item.get("hash_id", f"hash_{idx}")
            paper = Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=self.pipeline_run,
                hash_id=hash_id,
                title=item.get("title", f"Paper {idx}"),
                abstract=item.get("abstract", f"Abstract {idx}"),
                authors=item.get("authors", "Author et al."),
                doi=item.get("doi"),
                arxiv_id=item.get("arxiv_id"),
                source_database=item.get("source_database", "arxiv"),
                original_pdf_path=item.get("original_pdf_path", f"https://arxiv.org/pdf/{hash_id}.pdf"),
                screening_status="pending"
            )
            self.papers.append(paper)

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        return self

    def complete_step_2_download(self, failed_paper_indices: list[int] | None = None) -> "PipelineTestHarness":
        """Simulates completing Step 2 (PDF Binary Download) with optional download failures."""
        failed_indices = set(failed_paper_indices or [])
        dl_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='download')
        downloaded_count = len(self.papers) - len(failed_indices)

        for run in dl_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'downloaded': downloaded_count, 'failed': len(failed_indices)}
            run.save()

        for idx, p in enumerate(self.papers):
            if idx in failed_indices:
                p.screening_status = 'withdrawn'
                p.screening_reasoning = "Failed to download PDF: 404 Not Found at source."
                p.save(update_fields=['screening_status', 'screening_reasoning'])
            else:
                pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{p.hash_id}/original.pdf"
                default_storage.save(pdf_path, ContentFile(b"%PDF-1.4 Mock Binary Data"))
                p.original_pdf_path = pdf_path
                p.save(update_fields=['original_pdf_path'])

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        return self

    def complete_step_3_ocr_if_needed(self, failed_paper_indices: list[int] | None = None) -> "PipelineTestHarness":
        """Simulates completing Step 3 (OCR Conversion) if workspace has an OCR provider."""
        failed_indices = set(failed_paper_indices or [])
        if self.workspace.ocr_provider and str(self.workspace.ocr_provider).lower() != 'none':
            ocr_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='ocr')
            active_papers = [p for idx, p in enumerate(self.papers) if idx not in failed_indices and p.screening_status != 'withdrawn']

            for run in ocr_runs:
                run.status = 'completed'
                run.completed_at = timezone.now()
                run.metrics = {'converted': len(active_papers), 'failed': len(failed_indices)}
                run.save()

            for idx, p in enumerate(self.papers):
                if idx not in failed_indices and p.screening_status != 'withdrawn':
                    md_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{p.hash_id}/ocr.md"
                    default_storage.save(md_path, ContentFile(b"# Extracted Markdown Content"))
                    p.converted_md_path = md_path
                    p.save(update_fields=['converted_md_path'])

            # Trigger tick to advance
            self._tick()
            self.agent_process.refresh_from_db()

        return self

    def complete_step_4a_abstract_screening(self, passed_paper_indices: list[int]) -> "PipelineTestHarness":
        """Simulates completing Stage 4a (Abstract Screening)."""
        abs_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='screening', component_name__icontains='abstract')
        passed_count = len(passed_paper_indices)
        rejected_count = len(self.papers) - passed_count

        for run in abs_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'total_screened': len(self.papers), 'passed': passed_count, 'rejected': rejected_count}
            run.save()

        for idx, p in enumerate(self.papers):
            if idx in passed_paper_indices:
                p.screening_status = 'abstract_passed'
            else:
                p.screening_status = 'rejected'
            p.save(update_fields=['screening_status'])

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        return self

    def complete_step_4b_full_text_screening(self, passed_paper_indices: list[int]) -> "PipelineTestHarness":
        """Simulates completing Stage 4b (Full-Text Screening)."""
        ft_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='screening', component_name__icontains='full_text')
        passed_count = len(passed_paper_indices)

        for run in ft_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'total_screened': len(self.papers), 'passed': passed_count, 'rejected': len(self.papers) - passed_count}
            run.save()

        for idx, p in enumerate(self.papers):
            if idx in passed_paper_indices:
                p.screening_status = 'full_text_passed'
            else:
                p.screening_status = 'rejected'
            p.save(update_fields=['screening_status'])

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        return self

    def complete_step_5_extraction(self, sample_extracted_fields: dict | None = None) -> "PipelineTestHarness":
        """Simulates completing Step 5 (Parameter Extraction) for all passed papers."""
        ext_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='extraction')
        passed_papers = [p for p in self.papers if p.screening_status in ['full_text_passed', 'abstract_passed', 'accepted']]

        for run in ext_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {
                'total_papers': len(passed_papers),
                'total_definitions': len(self.extraction_definitions),
                'extractions_created': len(passed_papers) * len(self.extraction_definitions)
            }
            run.save()

        fields = sample_extracted_fields or {"result": "Validated 99.2% Accuracy"}
        for p in passed_papers:
            for ed in self.extraction_definitions:
                Extraction.objects.create(
                    workspace=self.workspace,
                    paper=p,
                    extraction_definition=ed,
                    category=ed.name,
                    fields_data=fields,
                    validation_status="pass",
                    confidence_score=0.95
                )

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
        return self

    def inject_failure_at_current_step(self, error_message: str = "Simulated upstream failure") -> "PipelineTestHarness":
        """Simulates an unrecoverable failure in active component runs of the current step."""
        active_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, status__in=['pending', 'running'])
        for run in active_runs:
            run.status = 'failed'
            run.error_message = error_message
            run.completed_at = timezone.now()
            run.save()

        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
        return self

    def get_step_names_history(self) -> list[str]:
        """Returns the list of step names traversed in step_history."""
        return [entry.get("step") for entry in (self.agent_process.step_history or [])]
