import logging
from typing import Optional, Dict, Any
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from celery import shared_task

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    Extraction,
    NarrativeReport,
)

logger = logging.getLogger(__name__)


def generate_executive_narrative_report(pipeline_run: PipelineRun) -> Dict[str, Any]:
    """
    Synthesizes a structured Systematic Literature Review (SLR) executive narrative report
    from all accepted papers, extractions, and composite signal scores.
    Saves a NarrativeReport DB record and stores the markdown artifact in default_storage.
    """
    workspace = pipeline_run.workspace
    ws_name = workspace.name if workspace else "Research Workspace"
    run_date_str = (
        pipeline_run.started_at.strftime("%B %d, %Y %H:%M UTC")
        if pipeline_run.started_at
        else timezone.now().strftime("%B %d, %Y %H:%M UTC")
    )

    # 1. Fetch papers
    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).prefetch_related(
        'extractions', 'extractions__extraction_definition'
    ).order_by('-created_at')

    # Determine truly accepted papers based on terminal screening status
    if papers_qs.filter(screening_status__in=['full_text_passed', 'accepted']).exists():
        accepted_papers = list(papers_qs.filter(screening_status__in=['full_text_passed', 'accepted']))
    elif papers_qs.filter(screening_status='abstract_passed').exists():
        accepted_papers = list(papers_qs.filter(screening_status='abstract_passed'))
    else:
        accepted_papers = list(papers_qs.exclude(screening_status__in=['rejected', 'withdrawn', 'pending']))

    # Sort: highest signal_score first
    accepted_papers.sort(
        key=lambda p: (
            p.signal_score is not None,
            p.signal_score if p.signal_score is not None else -1.0,
            p.created_at
        ),
        reverse=True
    )

    total_papers = papers_qs.count() or (pipeline_run.total_papers_fetched or len(accepted_papers))
    rejected_count = max(0, total_papers - len(accepted_papers))
    scored_papers = [p for p in accepted_papers if p.signal_score is not None]
    avg_signal_score = (sum(p.signal_score for p in scored_papers) / len(scored_papers)) if scored_papers else 0.0

    # 2. Build Markdown Document
    lines = [
        f"# Executive Research Briefing: {ws_name}",
        f"**Pipeline Run Date**: {run_date_str}  ",
        f"**Run ID**: `{pipeline_run.id}`  ",
        f"**Total Papers Ingested**: {total_papers} | **Accepted**: {len(accepted_papers)} | **Rejected**: {rejected_count}  ",
        f"**Average Signal Score**: {avg_signal_score:.2f}  ",
        "",
        "---",
        "",
        "## 1. Executive Summary & Review Highlights",
        f"This automated systematic review screened **{total_papers}** scientific publications against the defined workspace criteria.",
        f"A total of **{len(accepted_papers)}** papers met the domain acceptance criteria and underwent dynamic parameter extraction and AST composite signal score ranking.",
        "",
        "## 2. Top-Ranked Breakthrough Papers",
        "",
    ]

    if accepted_papers:
        for idx, paper in enumerate(accepted_papers[:10], 1):
            score_badge = f"`Signal Score: {paper.signal_score:.2f}`" if paper.signal_score is not None else "`Unscored`"
            lines.append(f"### {idx}. {paper.title}")
            lines.append(f"- **Authors**: {paper.authors or 'N/A'}")
            lines.append(f"- **Source**: {paper.source_database.upper() if paper.source_database else 'ArXiv'} | {score_badge}")
            if paper.doi:
                lines.append(f"- **DOI**: [{paper.doi}](https://doi.org/{paper.doi})")
            if paper.arxiv_id:
                lines.append(f"- **arXiv**: [{paper.arxiv_id}](https://arxiv.org/abs/{paper.arxiv_id})")
            
            lines.append(f"- **Screening Decision**: `{paper.screening_status}`")
            if paper.screening_reasoning:
                lines.append(f"- **Assessment Rationale**: {paper.screening_reasoning}")

            # Include parameter extractions
            extractions = list(paper.extractions.all())
            if extractions:
                lines.append("- **Extracted Parameters**:")
                for ext in extractions:
                    def_name = ext.extraction_definition.name if ext.extraction_definition else ext.category
                    exit_val = ext.exit_metric or "N/A"
                    lines.append(f"  - **{def_name}**: `{exit_val}` (confidence: {ext.confidence_score or 1.0:.2f})")
            lines.append("")
    else:
        lines.append("*No papers passed screening criteria during this run.*")
        lines.append("")

    lines.extend([
        "## 3. Resource & Pipeline Execution Trace",
        f"- **Execution Time**: {pipeline_run.execution_time_display}",
        f"- **Tokens Consumed**: {pipeline_run.tokens_consumed or 0:,}",
        f"- **Estimated USD Cost**: ${float(pipeline_run.usd_cost or 0.0):.4f}",
        "",
        "---",
        "*Generated automatically by Schwarz Research Intelligence Platform.*",
    ])

    report_markdown = "\n".join(lines)

    # 3. Save Markdown to storage: workspaces/{ws_id}/runs/{run_id}/narrative_report.md
    target_storage_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/narrative_report.md"
    default_storage.save(target_storage_path, ContentFile(report_markdown.encode('utf-8')))

    # 4. Save NarrativeReport record
    report_title = f"Executive Briefing - {ws_name} ({run_date_str})"
    narrative_report, _ = NarrativeReport.objects.update_or_create(
        pipeline_run=pipeline_run,
        defaults={
            "workspace": workspace,
            "title": report_title,
            "content_markdown": report_markdown,
            "refinement_depth": 1,
        }
    )

    logger.info(f"✅ Generated NarrativeReport '{narrative_report.id}' at '{target_storage_path}'.")
    return {
        "success": True,
        "report_id": str(narrative_report.id),
        "title": report_title,
        "storage_path": target_storage_path,
        "characters_count": len(report_markdown),
    }


@shared_task
def generate_narrative_report_with_refinement(workspace_id):
    """Backwards-compatible Celery task."""
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        latest_run = workspace.pipeline_runs.order_by('-started_at').first()
        if latest_run:
            return generate_executive_narrative_report(latest_run)
    except Exception as e:
        logger.warning(f"Failed generate_narrative_report_with_refinement for ws {workspace_id}: {e}")
    return True
