import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from celery.app.task import Task

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


class CeleryTaskIntrospector:
    """
    Introspective Celery Task Interceptor.
    Uses dynamic method interception on the base `celery.app.task.Task` class rather than brittle,
    hardcoded module patch lists. Automatically discovers and intercepts every task in the pipeline.
    """

    def __init__(self):
        self.dispatched_tasks: list[dict] = []

    @contextmanager
    def intercept(self):
        """Intercepts all Celery task dispatch calls and records them into self.dispatched_tasks."""
        def fake_apply_async(task_self, args=None, kwargs=None, *a, **kw):
            task_name = getattr(task_self, "name", str(task_self))
            record = {"task": task_name, "args": args or (), "kwargs": kwargs or {}}
            self.dispatched_tasks.append(record)
            mock_res = MagicMock()
            mock_res.id = f"mock_task_{len(self.dispatched_tasks)}"
            return mock_res

        def fake_delay(task_self, *args, **kwargs):
            return fake_apply_async(task_self, args=args, kwargs=kwargs)

        with patch.object(Task, "apply_async", fake_apply_async), \
             patch.object(Task, "delay", fake_delay), \
             patch("research_intelligence.tasks.orchestrator.agent_engine._send_agent_notification"):
            yield self


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
        self.introspector = CeleryTaskIntrospector()

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
        """Executes tick_agent_process with dynamic Celery task introspection."""
        with self.introspector.intercept():
            return tick_agent_process(str(self.agent_process.id))

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
        self.pipeline_run.refresh_from_db()
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
                pdf_bytes = b"%PDF-1.4 Mock Binary Data for Harness Testing"
                pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{p.hash_id}/original.pdf"
                from research_intelligence.tasks.step_2_download.pdf_cache import try_reuse_cached_pdf, register_document_pdf
                cache_hit = try_reuse_cached_pdf(p, pdf_path)
                if not cache_hit:
                    default_storage.save(pdf_path, ContentFile(pdf_bytes))
                    p.original_pdf_path = pdf_path
                    p.save(update_fields=['original_pdf_path'])
                    register_document_pdf(p, pdf_bytes)

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
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
                    md_bytes = b"# Extracted Markdown Content from Harness"
                    md_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{p.hash_id}/ocr.md"
                    default_storage.save(md_path, ContentFile(md_bytes))
                    p.converted_md_path = md_path
                    p.save(update_fields=['converted_md_path'])
                    p.refresh_from_db()
                    if p.document_registry:
                        p.document_registry.ocr_provider = self.workspace.ocr_provider
                        canonical_ocr_path = f"cache/documents/{p.document_registry.sha256_hash}/ocr_{self.workspace.ocr_provider}.md"
                        default_storage.save(canonical_ocr_path, ContentFile(md_bytes))
                        p.document_registry.canonical_ocr_md_path = canonical_ocr_path
                        p.document_registry.save(update_fields=['ocr_provider', 'canonical_ocr_md_path'])

            # Trigger tick to advance
            self._tick()
            self.agent_process.refresh_from_db()
            self.pipeline_run.refresh_from_db()

        return self

    def complete_step_3_ocr(self, failed_paper_indices: list[int] | None = None) -> "PipelineTestHarness":
        """Alias for complete_step_3_ocr_if_needed."""
        return self.complete_step_3_ocr_if_needed(failed_paper_indices=failed_paper_indices)

    def complete_step_4a_abstract_screening(
        self,
        passed_paper_indices: list[int],
        tokens_in: int = 0,
        tokens_out: int = 0,
        usd_cost: float = 0.0
    ) -> "PipelineTestHarness":
        """Simulates completing Stage 4a (Abstract Screening)."""
        abs_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='screening', component_name__icontains='abstract')
        passed_count = len(passed_paper_indices)
        rejected_count = len(self.papers) - passed_count

        for run in abs_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'total_screened': len(self.papers), 'passed': passed_count, 'rejected': rejected_count}
            if tokens_in or tokens_out or usd_cost:
                run.output_data = {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'usd_cost': usd_cost}
            run.save()

        if tokens_in or tokens_out or usd_cost:
            self.pipeline_run.tokens_in = (self.pipeline_run.tokens_in or 0) + tokens_in
            self.pipeline_run.tokens_out = (self.pipeline_run.tokens_out or 0) + tokens_out
            self.pipeline_run.tokens_consumed = self.pipeline_run.tokens_in + self.pipeline_run.tokens_out
            self.pipeline_run.usd_cost = float(self.pipeline_run.usd_cost or 0) + usd_cost
            self.pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost'])

        for idx, p in enumerate(self.papers):
            if idx in passed_paper_indices:
                p.screening_status = 'abstract_passed'
            else:
                p.screening_status = 'rejected'
            p.save(update_fields=['screening_status'])

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
        return self

    def complete_step_4b_full_text_screening(
        self,
        passed_paper_indices: list[int],
        tokens_in: int = 0,
        tokens_out: int = 0,
        usd_cost: float = 0.0
    ) -> "PipelineTestHarness":
        """Simulates completing Stage 4b (Full-Text Screening)."""
        ft_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='screening', component_name__icontains='full_text')
        passed_count = len(passed_paper_indices)

        for run in ft_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'total_screened': len(self.papers), 'passed': passed_count, 'rejected': len(self.papers) - passed_count}
            if tokens_in or tokens_out or usd_cost:
                run.output_data = {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'usd_cost': usd_cost}
            run.save()

        if tokens_in or tokens_out or usd_cost:
            self.pipeline_run.tokens_in = (self.pipeline_run.tokens_in or 0) + tokens_in
            self.pipeline_run.tokens_out = (self.pipeline_run.tokens_out or 0) + tokens_out
            self.pipeline_run.tokens_consumed = self.pipeline_run.tokens_in + self.pipeline_run.tokens_out
            self.pipeline_run.usd_cost = float(self.pipeline_run.usd_cost or 0) + usd_cost
            self.pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost'])

        for idx, p in enumerate(self.papers):
            if idx in passed_paper_indices:
                p.screening_status = 'full_text_passed'
            else:
                p.screening_status = 'rejected'
            p.save(update_fields=['screening_status'])

        # Trigger tick to advance
        self._tick()
        self.agent_process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
        return self

    def complete_step_5_extraction(
        self,
        sample_extracted_fields: dict | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        usd_cost: float = 0.0
    ) -> "PipelineTestHarness":
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
            if tokens_in or tokens_out or usd_cost:
                run.output_data = {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'usd_cost': usd_cost}
            run.save()

        if tokens_in or tokens_out or usd_cost:
            self.pipeline_run.tokens_in = (self.pipeline_run.tokens_in or 0) + tokens_in
            self.pipeline_run.tokens_out = (self.pipeline_run.tokens_out or 0) + tokens_out
            self.pipeline_run.tokens_consumed = self.pipeline_run.tokens_in + self.pipeline_run.tokens_out
            self.pipeline_run.usd_cost = float(self.pipeline_run.usd_cost or 0) + usd_cost
            self.pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost'])

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

        if self.agent_process.current_step == 'signal_score':
            self.complete_step_6_signal_score()

        return self

    def complete_step_6_signal_score(self) -> "PipelineTestHarness":
        """Simulates completing Step 6 (Signal Score Evaluation)."""
        sig_runs = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type='signal_score')
        for run in sig_runs:
            run.status = 'completed'
            run.completed_at = timezone.now()
            run.metrics = {'scored_count': len(self.papers), 'avg_signal_score': 85.0}
            run.save()

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
