"""
Seed a local Django backend with a demo workspace for frontend development.

Run from the backend checkout, against its own settings (SQLite when DB_HOST
is unset):

    cd ../schwarz-research-intelligence/backend
    python manage.py migrate
    python manage.py createsuperuser        # the account you log in with
    python manage.py shell < ../../research-scanner/scripts/seed-django.py

Idempotent by workspace name. Creates: one workspace with a signal-score
formula, three extraction definitions (Fit Score, Novelty Score, TRL Level),
a completed pipeline run, ten papers with mixed screening statuses, and
extractions in both the flat and nested field shapes — including one
non-numeric value and one unscored paper — then computes signal scores for
the papers that passed screening.
"""

import os
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from research_intelligence.models import (
    Extraction,
    ExtractionDefinition,
    Paper,
    PipelineRun,
    Workspace,
    WorkspaceMember,
)
from research_intelligence.tasks.step_6_signal_score.scorer import compute_paper_signal_score

User = get_user_model()

WORKSPACE_NAME = os.environ.get("SEED_WORKSPACE", "Agentic AI Scan (demo)")
SEED_USERNAME = os.environ.get("SEED_USER")  # defaults to the first superuser

user = (
    User.objects.filter(username=SEED_USERNAME).first()
    if SEED_USERNAME
    else User.objects.filter(is_superuser=True).order_by("id").first()
)
if user is None:
    raise SystemExit("No user found — run `python manage.py createsuperuser` first.")

workspace, created = Workspace.objects.get_or_create(
    name=WORKSPACE_NAME,
    defaults=dict(
        abstract_acceptance_criteria="Agentic AI systems, multi-agent orchestration, tool use",
        abstract_rejection_criteria="Pure surveys without new results",
        full_text_acceptance_criteria="Reported evaluation on a benchmark or deployment",
        full_text_rejection_criteria="No empirical evaluation",
        screening_llm_model="google/gemini-3.7-flash",
        ocr_provider=None,
        signal_score_code=(
            "k = 6 * fit_score + 4 * novelty_score + 2 * trl_level\n"
            "return min(100.0, k)\n"
        ),
    ),
)
WorkspaceMember.objects.get_or_create(workspace=workspace, user=user, defaults={"role": "admin"})

def definition(name, exit_metric, prompt):
    obj, _ = ExtractionDefinition.objects.get_or_create(
        workspace=workspace,
        name=name,
        defaults=dict(
            exit_metric=exit_metric,
            system_prompt=prompt,
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"},
        ),
    )
    return obj

def_fit = definition("Fit Score", "fit_score", "Rate strategic fit for a retail group (1-10).")
def_nov = definition("Novelty Score", "novelty_score", "Rate novelty versus prior work (1-10).")
def_trl = definition("TRL Level", "trl_level", "Estimate the technology readiness level (1-9).")

if created or not workspace.pipeline_runs.exists():
    now = timezone.now()
    run = PipelineRun.objects.create(
        workspace=workspace,
        status="completed",
        current_stage="completed",
        total_papers_fetched=48,
        total_papers_passed_screening=7,
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=1),
        triggered_by=user,
        status_message="Completed: 48 fetched, 7 passed screening.",
    )

    PAPERS = [
        # title, authors, arxiv_id, status, fit, novelty, trl (None = no extraction)
        ("Deterministic Control Flow for Tool-Using Agents", "Alice Quantum, Bob Builder, Carol Chen", "2603.30117", "full_text_passed", "9", "8", "TRL 4"),
        ("Recovery-First Tool Use: Making Agent Failures Cheap", "Dana Ortiz and Evan Li", "2603.28801", "full_text_passed", "8", "7", "TRL 5"),
        ("A Learned Memory Controller at a Sixth of the Tokens", "Farah Nasser; Greg Holt", "2603.27760", "full_text_passed", "7", "9", "TRL 3"),
        ("Verifiable Delegation for Agents at Checkout", "Hiro Tanaka, Ines Weber", "2603.26644", "full_text_passed", "9", "6", "TRL 6"),
        ("Durable Content Credentials Through Platform Pipelines", "Jonas Keller", "2603.25502", "abstract_passed", "6", "5", "TRL 7"),
        ("Benchmarking Multi-Agent Planners in Warehouses", "Kim Park, Lars Meyer", "2603.24410", "accepted", "7", "4", "TRL 5"),
        ("Self-Correcting SQL Agents for Retail Analytics", "Mira Sato", "2603.23399", "full_text_passed", "High", "6", "TRL 4"),
        ("On the Limits of Prompt-Only Guardrails", "Nikhil Rao, Olga Petrova", "2603.22288", "borderline", "5", "5", "TRL 2"),
        ("A Survey of Agent Frameworks (2020–2026)", "Paula Diaz", "2603.21177", "rejected", None, None, None),
        ("Scheduled Reasoning Budgets for Long-Horizon Agents", "Quinn Adebayo, Rosa Lindqvist", "2603.20066", "pending", None, None, None),
    ]

    for i, (title, authors, arxiv_id, status, fit, nov, trl) in enumerate(PAPERS):
        paper = Paper.objects.create(
            workspace=workspace,
            pipeline_run=run,
            hash_id=uuid.uuid4().hex,
            title=title,
            authors=authors,
            arxiv_id=arxiv_id,
            source_database="arxiv",
            screening_status=status,
            screening_reasoning=(
                "Rejected: survey without new empirical results."
                if status == "rejected"
                else "Not yet screened."
                if status == "pending"
                else "Meets the acceptance criteria: agentic system with a reported evaluation."
            ),
            abstract=(
                f"{title}. We study agentic systems for retail and logistics settings and report "
                "an evaluation against a public benchmark, with ablations on tool selection, "
                "recovery behaviour, and cost per task."
            ),
            original_pdf_path=f"workspaces/{workspace.id}/runs/{run.id}/documents/{i:02d}/original.pdf",
        )
        if fit is None:
            continue
        # Flat fields with sibling reasoning/evidence keys (the extraction step's usual output).
        Extraction.objects.create(
            workspace=workspace,
            paper=paper,
            extraction_definition=def_fit,
            category=def_fit.name,
            fields_data={
                "fit_score": fit,
                "reasoning": "Directly applicable to store operations and logistics tooling.",
                "evidence_quotes": ["deployed in a pilot across three distribution centres"],
                "confidence_score": 0.82,
            },
            validation_status="pass",
            confidence_score=0.82,
        )
        # Nested field form with value/confidence/evidence objects.
        Extraction.objects.create(
            workspace=workspace,
            paper=paper,
            extraction_definition=def_nov,
            category=def_nov.name,
            fields_data={
                "fields": {
                    "novelty_score": {
                        "value": int(nov),
                        "normalized_value": f"{nov}/10",
                        "confidence": 0.7,
                        "evidence": [
                            {
                                "quote": "to our knowledge the first learned controller of this kind",
                                "rationale": "Claims novelty against the cited prior work.",
                            }
                        ],
                    }
                }
            },
            validation_status="warn" if int(nov) >= 8 else "pass",
            review_required=int(nov) >= 8,
            confidence_score=0.7,
        )
        Extraction.objects.create(
            workspace=workspace,
            paper=paper,
            extraction_definition=def_trl,
            category=def_trl.name,
            fields_data={"trl_level": trl, "trl_reasoning": "Pilot deployment reported; no production scale yet."},
            validation_status="pass",
        )

    for paper in run.papers.filter(screening_status__in=["accepted", "full_text_passed", "abstract_passed"]):
        compute_paper_signal_score(paper, pipeline_run=run)

print(f"Seeded workspace '{workspace.name}' ({workspace.id}) for user '{user.username}'.")
print(f"Papers: {workspace.papers.count()}, extractions: {Extraction.objects.filter(workspace=workspace).count()}")
