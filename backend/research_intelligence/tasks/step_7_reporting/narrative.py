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


def _annotate_papers(papers_qs, pipeline_run: PipelineRun):
    from django.db.models import Subquery, OuterRef
    from research_intelligence.models import PaperMetric
    metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run=pipeline_run)
    return list(papers_qs.annotate(
        annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1]),
        annotated_screening_status=Subquery(metric_sub.values('screening_status')[:1]),
        annotated_abstract_screening_reasoning=Subquery(metric_sub.values('abstract_screening_reasoning')[:1]),
        annotated_full_text_screening_reasoning=Subquery(metric_sub.values('full_text_screening_reasoning')[:1]),
    ).prefetch_related('extractions', 'extractions__extraction_definition').order_by('-created_at'))


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

    # 1. Fetch papers with run-specific signal scores
    from django.db.models import Subquery, OuterRef
    from research_intelligence.models import PaperMetric
    metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run=pipeline_run)
    papers_qs = pipeline_run.get_papers().annotate(
        annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1]),
        annotated_screening_status=Subquery(metric_sub.values('screening_status')[:1])
    ).prefetch_related(
        'extractions', 'extractions__extraction_definition'
    ).order_by('-created_at')

    # Determine truly accepted papers based on terminal screening status
    accepted_papers = _annotate_papers(pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted']), pipeline_run)
    if not accepted_papers:
        accepted_papers = _annotate_papers(pipeline_run.get_papers(screening_status='abstract_passed'), pipeline_run)
    if not accepted_papers:
        accepted_papers = _annotate_papers(pipeline_run.get_papers(exclude_status=['rejected', 'withdrawn', 'pending']), pipeline_run)

    # Sort: highest signal_score first
    accepted_papers.sort(
        key=lambda p: (
            getattr(p, 'annotated_signal_score', None) is not None,
            getattr(p, 'annotated_signal_score', None) if getattr(p, 'annotated_signal_score', None) is not None else -1.0,
            p.created_at
        ),
        reverse=True
    )

    total_papers = papers_qs.count() or (pipeline_run.total_papers_fetched or len(accepted_papers))
    rejected_count = max(0, total_papers - len(accepted_papers))
    scored_papers = [p for p in accepted_papers if getattr(p, 'annotated_signal_score', None) is not None]
    avg_signal_score = (sum(getattr(p, 'annotated_signal_score', 0.0) for p in scored_papers) / len(scored_papers)) if scored_papers else 0.0

    # 2. Build or Synthesize Markdown Document
    custom_prompt = workspace.get_narrative_report_prompt() if workspace else None
    report_markdown = None

    if custom_prompt and accepted_papers:
        try:
            import json
            from research_intelligence.utils.prompt_formatter import safe_format_prompt
            from research_intelligence.tasks.step_6_signal_score.scorer import extract_paper_parameters
            from research_intelligence.llm_providers import get_llm_provider

            top_n = workspace.get_narrative_report_top_n_papers()
            top_papers = accepted_papers[:top_n]

            papers_data_list = []
            papers_text_blocks = []
            all_score_vectors_dict = {}

            for idx, paper in enumerate(top_papers, 1):
                s_score = getattr(paper, 'annotated_signal_score', None)
                if s_score is not None:
                    s_score = round(float(s_score), 2)

                score_vectors = extract_paper_parameters(paper, pipeline_run)
                all_score_vectors_dict[str(paper.id)] = score_vectors

                ext_list = []
                for ext in paper.extractions.all():
                    d_name = ext.extraction_definition.name if ext.extraction_definition else (ext.category or "Param")
                    ext_list.append({
                        "name": d_name,
                        "value": ext.exit_metric or "",
                        "confidence": float(ext.confidence_score) if ext.confidence_score is not None else None,
                    })

                p_dict = {
                    "rank": idx,
                    "id": str(paper.id),
                    "title": paper.title or "Untitled",
                    "abstract": paper.abstract or "",
                    "authors": paper.authors or "",
                    "doi": paper.doi or "",
                    "arxiv_id": paper.arxiv_id or "",
                    "source": paper.source_database or "arxiv",
                    "source_url": paper.source_url or "",
                    "signal_score": s_score,
                    "score_vectors": score_vectors,
                    "extractions": ext_list,
                }
                papers_data_list.append(p_dict)

                source_info = f"- Source: {p_dict['source'].upper()}"
                details = []
                if paper.source_url:
                    details.append(f"URL: {paper.source_url}")
                if p_dict['doi']:
                    details.append(f"DOI: {p_dict['doi']}")
                if p_dict['arxiv_id']:
                    details.append(f"arXiv: {p_dict['arxiv_id']}")
                if details:
                    source_info += f" ({', '.join(details)})"

                lines_p = [
                    f"### [{idx}] {p_dict['title']}",
                    f"- Signal Score: {s_score if s_score is not None else 'N/A'}",
                    f"- Authors: {p_dict['authors'] or 'N/A'}",
                    source_info,
                    f"- Score Vectors: {json.dumps(score_vectors)}",
                    f"- Abstract: {p_dict['abstract']}",
                ]
                papers_text_blocks.append("\n".join(lines_p))

            prompt_context = {
                "workspace_name": ws_name,
                "run_date": run_date_str,
                "run_id": str(pipeline_run.id),
                "total_papers": total_papers,
                "accepted_papers_count": len(accepted_papers),
                "rejected_papers_count": rejected_count,
                "avg_signal_score": round(avg_signal_score, 2),
                "top_n_papers_count": len(top_papers),
                "papers": "\n\n".join(papers_text_blocks),
                "papers_json": json.dumps(papers_data_list, indent=2),
                "score_vectors_summary": json.dumps(all_score_vectors_dict, indent=2),
            }

            formatted_prompt = safe_format_prompt(custom_prompt, prompt_context)
            system_instruction = workspace.get_narrative_report_system_prompt()
            llm_provider = get_llm_provider(workspace.llm_provider)
            llm_model = workspace.screening_llm_model or "google/gemini-3.8-flash"

            logger.info(f"🤖 Synthesizing custom Executive Narrative Report via LLM ({llm_model}) for {len(top_papers)} top papers...")
            generated_text = llm_provider.generate(
                prompt=formatted_prompt,
                system_instruction=system_instruction,
                model=llm_model,
            )
            if generated_text and generated_text.strip():
                report_markdown = generated_text.strip()
                logger.info("✅ Custom Executive Narrative Report successfully synthesized by LLM.")
        except Exception as e:
            logger.warning(f"⚠️ Custom narrative report LLM generation failed ({e}). Falling back to standard template.")

    if not report_markdown:
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
                s_score = getattr(paper, 'annotated_signal_score', None)
                score_badge = f"`Signal Score: {s_score:.2f}`" if s_score is not None else "`Unscored`"
                lines.append(f"### {idx}. {paper.title}")
                lines.append(f"- **Authors**: {paper.authors or 'N/A'}")
                lines.append(f"- **Source**: {paper.source_database.upper() if paper.source_database else 'ArXiv'} | {score_badge}")
                if paper.doi:
                    lines.append(f"- **DOI**: [{paper.doi}](https://doi.org/{paper.doi})")
                if paper.arxiv_id:
                    lines.append(f"- **arXiv**: [{paper.arxiv_id}](https://arxiv.org/abs/{paper.arxiv_id})")

                status_display = getattr(paper, 'annotated_screening_status', None) or 'pending'
                lines.append(f"- **Screening Decision**: `{status_display}`")
                abs_reason = getattr(paper, 'annotated_abstract_screening_reasoning', None)
                if abs_reason:
                    lines.append(f"- **Abstract Screening Rationale**: {abs_reason}")
                ft_reason = getattr(paper, 'annotated_full_text_screening_reasoning', None)
                if ft_reason:
                    lines.append(f"- **Full-Text Screening Rationale**: {ft_reason}")

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
            f"*Generated automatically by {getattr(settings, 'APP_NAME', 'Schwarz Research Intelligence')} Platform.*",
        ])

        report_markdown = "\n".join(lines)

    # 3. Save Markdown to storage: workspaces/{ws_id}/runs/{run_id}/narrative_report.md
    target_storage_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/narrative_report.md"
    if default_storage.exists(target_storage_path):
        default_storage.delete(target_storage_path)
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


@shared_task(acks_late=True, reject_on_worker_lost=True)
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
