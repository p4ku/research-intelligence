import logging
from typing import Optional, List, Dict, Any
from django.db import close_old_connections
from django.utils import timezone
from celery import shared_task
from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    Extraction,
    Subscriber,
)
from research_intelligence.utils.mailer import send_mailgun_message

logger = logging.getLogger(__name__)


def build_pipeline_run_digest_payload(pipeline_run: PipelineRun) -> Dict[str, Any]:
    """
    Gathers metrics, papers, extractions, and definitions for an executed PipelineRun
    and generates both state-of-the-art responsive HTML and clean plaintext email content.
    """
    workspace = pipeline_run.workspace
    ws_name = workspace.name if workspace else "Research Workspace"
    run_date_str = (
        pipeline_run.started_at.strftime("%B %d, %Y %H:%M UTC")
        if pipeline_run.started_at
        else timezone.now().strftime("%B %d, %Y")
    )
    duration_str = pipeline_run.execution_time_display

    # 1. Fetch papers and extractions
    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).prefetch_related(
        'extractions', 'extractions__extraction_definition'
    ).order_by('-created_at')

    total_papers = papers_qs.count()
    accepted_papers = [
        p for p in papers_qs
        if p.screening_status in ['accepted', 'full_text_passed', 'abstract_passed']
    ]
    rejected_count = total_papers - len(accepted_papers)

    # 2. Gather extractions
    extractions_qs = Extraction.objects.filter(paper__pipeline_run=pipeline_run).select_related(
        'paper', 'extraction_definition'
    )
    total_extractions = extractions_qs.count()

    cost_val = float(pipeline_run.usd_cost or 0.0)
    tokens_val = int(pipeline_run.tokens_consumed or 0)

    # 3. Build papers scorecard items
    papers_data = []
    for p in accepted_papers[:15]:  # top 15 in email digest for optimal reading length
        paper_exts = list(p.extractions.all())
        exts_list = []
        for ext in paper_exts:
            def_name = (
                ext.extraction_definition.name
                if ext.extraction_definition
                else (ext.category or "Parameter")
            )
            metric_val = ext.exit_metric or ext.get_exit_metric() or "Extracted"
            exts_list.append({
                "name": def_name,
                "value": metric_val,
                "confidence": ext.confidence_score,
                "status": ext.validation_status or "pass",
            })

        pdf_link = (
            f"https://arxiv.org/pdf/{p.arxiv_id}.pdf"
            if p.arxiv_id
            else (f"https://doi.org/{p.doi}" if p.doi else None)
        )

        papers_data.append({
            "title": p.title,
            "authors": p.authors or "Unknown Authors",
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "pdf_link": pdf_link,
            "screening_status": p.screening_status,
            "screening_reason": p.screening_reasoning or "",
            "extractions": exts_list,
        })

    # 4. Generate HTML Template
    papers_html_blocks = []
    for idx, paper in enumerate(papers_data, 1):
        ext_badges = []
        for ext in paper["extractions"]:
            status_color = "#10b981" if ext["status"] == "pass" else ("#f59e0b" if ext["status"] == "warn" else "#6b7280")
            conf_str = f" • {int(ext['confidence'] * 100)}%" if ext["confidence"] else ""
            ext_badges.append(
                f'<div style="display: inline-block; background: #f1f5f9; border-left: 3px solid {status_color}; padding: 6px 12px; margin: 4px 6px 4px 0; border-radius: 4px; font-size: 12px;">'
                f'<strong style="color: #334155;">{ext["name"]}:</strong> <span style="color: #0f172a; font-weight: 600;">{ext["value"]}</span>'
                f'<span style="color: #64748b; font-size: 11px;">{conf_str}</span>'
                f'</div>'
            )
        
        exts_markup = "".join(ext_badges) if ext_badges else '<span style="color: #94a3b8; font-size: 12px; font-style: italic;">No specific extraction parameters</span>'
        link_markup = f'<a href="{paper["pdf_link"]}" style="color: #2563eb; text-decoration: none; font-size: 12px; font-weight: 600;" target="_blank">📄 View Document &rarr;</a>' if paper["pdf_link"] else ''

        papers_html_blocks.append(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="font-size: 11px; font-weight: 700; color: #2563eb; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Paper #{idx} • {paper["screening_status"].replace('_', ' ').upper()}</div>
            </div>
            <h3 style="margin: 0 0 8px 0; font-size: 15px; font-weight: 700; color: #0f172a; line-height: 1.4;">
                {paper["title"]}
            </h3>
            <p style="margin: 0 0 12px 0; font-size: 12px; color: #64748b;">
                <strong>Authors:</strong> {paper["authors"]}
            </p>
            <div style="margin-top: 10px; margin-bottom: 12px;">
                {exts_markup}
            </div>
            {f'<div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">{link_markup}</div>' if link_markup else ''}
        </div>
        """)

    rendered_papers_html = "".join(papers_html_blocks) if papers_html_blocks else """
    <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;">
        No accepted papers passed criteria in this execution run.
    </div>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Research Digest] {ws_name}</title>
</head>
<body style="margin: 0; padding: 24px 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); border: 1px solid #e2e8f0;">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; padding: 32px 28px; text-align: left;">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="display: inline-block; background: #2563eb; color: #ffffff; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.5px; text-transform: uppercase;">
                    Systematic Review Complete
                </span>
                <span style="margin-left: auto; color: #10b981; font-size: 12px; font-weight: 600;">
                    🟢 COMPLETED
                </span>
            </div>
            <h1 style="margin: 8px 0 4px 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                {ws_name}
            </h1>
            <p style="margin: 0; font-size: 13px; color: #94a3b8;">
                Executive Literature Digest & Parameter Extraction Matrix • {run_date_str}
            </p>
        </div>

        <!-- 4-Card KPI Grid -->
        <div style="padding: 24px 28px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse: separate; border-spacing: 12px 0;">
                <tr>
                    <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                        <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;">Fetched</div>
                        <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-top: 4px;">{total_papers}</div>
                        <div style="font-size: 10px; color: #94a3b8; margin-top: 2px;">papers</div>
                    </td>
                    <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                        <div style="font-size: 11px; font-weight: 600; color: #10b981; text-transform: uppercase;">Accepted</div>
                        <div style="font-size: 20px; font-weight: 800; color: #10b981; margin-top: 4px;">{len(accepted_papers)}</div>
                        <div style="font-size: 10px; color: #94a3b8; margin-top: 2px;">{rejected_count} rejected</div>
                    </td>
                    <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                        <div style="font-size: 11px; font-weight: 600; color: #2563eb; text-transform: uppercase;">Extracted</div>
                        <div style="font-size: 20px; font-weight: 800; color: #2563eb; margin-top: 4px;">{total_extractions}</div>
                        <div style="font-size: 10px; color: #94a3b8; margin-top: 2px;">parameters</div>
                    </td>
                    <td width="25%" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                        <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;">Cost / Time</div>
                        <div style="font-size: 16px; font-weight: 800; color: #0f172a; margin-top: 6px;">${cost_val:.4f}</div>
                        <div style="font-size: 10px; color: #64748b; margin-top: 2px;">{duration_str}</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Body / Accepted Papers Scorecard -->
        <div style="padding: 28px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="margin: 0; font-size: 16px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px;">
                    🎯 Accepted Literature & Parameter Matrix
                </h2>
                <span style="font-size: 12px; color: #64748b; font-weight: 600;">
                    {len(accepted_papers)} papers verified
                </span>
            </div>

            {rendered_papers_html}

            <!-- Pipeline Execution Footprint -->
            <div style="margin-top: 28px; padding: 16px 20px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; font-size: 12px; color: #64748b; line-height: 1.6;">
                <strong>Pipeline Execution Run ID:</strong> <code>{str(pipeline_run.id)}</code><br>
                <strong>Token Footprint:</strong> {tokens_val:,} total tokens ({pipeline_run.tokens_in:,} prompt / {pipeline_run.tokens_out:,} completion)<br>
                <strong>Criteria Dual-Stage:</strong> Abstract & Multimodal Full-Text Screening with Gemini 3.7 Flash
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f1f5f9; padding: 20px 28px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0 0 6px 0;">
                You are receiving this automated research intelligence briefing because you are subscribed to <strong>{ws_name}</strong>.
            </p>
            <p style="margin: 0; color: #cbd5e1;">
                Schwarz Research Intelligence • Enterprise SLR Platform
            </p>
        </div>
    </div>
</body>
</html>
"""

    # Plain text alternative
    text_content = f"""
================================================================================
SCHWARZ RESEARCH INTELLIGENCE - SYSTEMATIC LITERATURE REVIEW DIGEST
================================================================================
Workspace: {ws_name}
Run ID: {str(pipeline_run.id)}
Date: {run_date_str}
Status: COMPLETED

METRICS SUMMARY:
- Total Papers Ingested: {total_papers}
- Screened Accepted: {len(accepted_papers)} (Rejected: {rejected_count})
- Parameters Extracted: {total_extractions}
- USD Cost: ${cost_val:.4f}
- Token Consumption: {tokens_val:,} tokens
- Total Duration: {duration_str}

ACCEPTED PAPERS & EXTRACTED PARAMETERS:
"""
    for idx, paper in enumerate(papers_data, 1):
        text_content += f"\n[{idx}] {paper['title']}\n"
        text_content += f"    Authors: {paper['authors']}\n"
        if paper['pdf_link']:
            text_content += f"    Link: {paper['pdf_link']}\n"
        for ext in paper['extractions']:
            text_content += f"    - {ext['name']}: {ext['value']} (Status: {ext['status']})\n"

    text_content += """
--------------------------------------------------------------------------------
Automated notification from Schwarz Research Intelligence Platform.
"""

    subject = f"[Research Digest] {ws_name} - Review Complete ({len(accepted_papers)} accepted papers)"

    return {
        "subject": subject,
        "html_content": html_content,
        "text_content": text_content,
        "stats": {
            "workspace_id": str(workspace.id) if workspace else None,
            "workspace_name": ws_name,
            "pipeline_run_id": str(pipeline_run.id),
            "total_papers": total_papers,
            "accepted_papers": len(accepted_papers),
            "rejected_papers": rejected_count,
            "total_extractions": total_extractions,
            "cost_usd": cost_val,
            "tokens_consumed": tokens_val,
        }
    }


def dispatch_pipeline_subscriber_digest(
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Main dispatch engine: Validates pipeline completion, gathers subscriber list,
    builds the rich executive email, and delivers messages via Mailgun.
    """
    close_old_connections()

    # 1. Resolve Workspace
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except (Workspace.DoesNotExist, ValueError):
        return {
            "status": "error",
            "error": f"Workspace '{workspace_id}' does not exist."
        }

    # 2. Resolve PipelineRun and validate completion
    try:
        pipeline_run = PipelineRun.objects.select_related('workspace').get(pk=pipeline_run_id, workspace=workspace)
    except (PipelineRun.DoesNotExist, ValueError):
        return {
            "status": "error",
            "error": f"PipelineRun '{pipeline_run_id}' does not exist in workspace '{workspace.name}'."
        }

    if pipeline_run.status != 'completed':
        # Check if pipeline run is still active or failed
        return {
            "status": "error",
            "error": (
                f"Cannot send digest: PipelineRun status is '{pipeline_run.status}'. "
                f"Digest emails can only be sent for 'completed' runs with verified parameters."
            )
        }

    # 3. Resolve Recipients
    recipients = []
    if recipient_override and isinstance(recipient_override, list):
        recipients = [e.strip() for e in recipient_override if e and "@" in e]
    else:
        subscribers = workspace.subscribers.filter(is_active=True)
        recipients = [s.email for s in subscribers if s.email]

    if not recipients:
        return {
            "status": "no_subscribers",
            "message": f"No active subscribers found for workspace '{workspace.name}', and no recipient override provided.",
            "workspace_id": str(workspace.id),
            "pipeline_run_id": str(pipeline_run.id),
            "sent_count": 0,
            "failed_count": 0,
            "recipients": []
        }

    # 4. Generate Digest Payload
    digest_payload = build_pipeline_run_digest_payload(pipeline_run)
    subject = digest_payload["subject"]
    html_body = digest_payload["html_content"]
    text_body = digest_payload["text_content"]

    # 5. Dispatch to each recipient via Mailgun
    sent_count = 0
    failed_count = 0
    delivery_results = []

    for email in recipients:
        success, resp_or_err = send_mailgun_message(
            to_email=email,
            subject=subject,
            text=text_body,
            html=html_body,
        )
        if success:
            sent_count += 1
            delivery_results.append({"email": email, "status": "sent", "response": resp_or_err})
            logger.info(f"📧 [DIGEST EMAIL SENT] Workspace '{workspace.name}' -> {email}")
        else:
            failed_count += 1
            delivery_results.append({"email": email, "status": "failed", "error": str(resp_or_err)})
            logger.error(f"❌ [DIGEST EMAIL FAILED] Workspace '{workspace.name}' -> {email}: {resp_or_err}")

    return {
        "status": "success" if sent_count > 0 else "failed",
        "workspace_id": str(workspace.id),
        "workspace_name": workspace.name,
        "pipeline_run_id": str(pipeline_run.id),
        "total_recipients": len(recipients),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "stats": digest_payload["stats"],
        "deliveries": delivery_results,
    }


@shared_task(name="tasks.auxiliary.send_pipeline_subscriber_digest_task", bind=True)
def send_pipeline_subscriber_digest_task(
    self,
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Celery background worker task for dispatching subscriber digest emails asynchronously.
    """
    logger.info(f"🚀 [TASK START] send_pipeline_subscriber_digest_task ws={workspace_id} run={pipeline_run_id}")
    res = dispatch_pipeline_subscriber_digest(workspace_id, pipeline_run_id, recipient_override)
    logger.info(f"🏁 [TASK FINISHED] send_pipeline_subscriber_digest_task ws={workspace_id} run={pipeline_run_id} status={res.get('status')}")
    return res
