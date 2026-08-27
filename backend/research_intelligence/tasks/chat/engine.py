import re
import json
import logging
from django.utils import timezone
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    Paper,
    Extraction,
    PaperMetric,
    PaperChatSession,
    PaperChatMessage,
    WorkspaceMember,
)
from research_intelligence.llm_providers import get_llm_provider
from research_intelligence.llm_providers.pricing import calculate_llm_cost

logger = logging.getLogger(__name__)


def build_paper_context(paper: Paper) -> tuple[str, bytes | None, str | None]:
    """
    Builds structured, concise paper context for LLM prompt:
    1. Metadata: Only present, non-empty attributes.
    2. Full document text: OCR Markdown if available, or raw PDF bytes for multimodal Gemini, or abstract.
    3. Screening evaluation: Only if evaluated or criteria defined.
    4. Extracted parameters: Only included if extractions exist (omits empty placeholder headers).
    5. Quality metrics & signal scores: Only included if metrics or score exist (omits empty placeholder headers).
    
    Returns (context_text, pdf_bytes, mime_type).
    """
    workspace = paper.workspace
    context_sections = []

    # 1. Basic Metadata (Only non-empty fields)
    meta_lines = ["### Paper Metadata", f"- Title: {paper.title}"]
    if paper.authors and paper.authors.strip():
        meta_lines.append(f"- Authors: {paper.authors.strip()}")
    if paper.doi and paper.doi.strip():
        meta_lines.append(f"- DOI: {paper.doi.strip()}")
    if paper.arxiv_id and paper.arxiv_id.strip():
        meta_lines.append(f"- arXiv ID: {paper.arxiv_id.strip()}")
    if paper.source_database and paper.source_database.strip():
        meta_lines.append(f"- Source: {paper.source_database.strip()}")
    if paper.pipeline_run_id:
        meta_lines.append(f"- Ingestion Run: {paper.pipeline_run_id}")
    context_sections.append("\n".join(meta_lines))

    # 2. Document Content (OCR Markdown vs Multimodal PDF vs Abstract)
    pdf_bytes = None
    mime_type = None

    has_md = False
    if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
        try:
            with default_storage.open(paper.converted_md_path, 'r') as f:
                md_text = f.read()
                if isinstance(md_text, bytes):
                    md_text = md_text.decode('utf-8', errors='replace')
                if md_text and len(md_text.strip()) > 50:
                    context_sections.append(f"### Full Document Text (Layout OCR Markdown):\n{md_text.strip()}")
                    has_md = True
        except Exception as e:
            logger.warning(f"Could not read OCR Markdown at '{paper.converted_md_path}': {e}")

    if not has_md and paper.original_pdf_path and default_storage.exists(paper.original_pdf_path):
        try:
            with default_storage.open(paper.original_pdf_path, 'rb') as f:
                pdf_bytes = f.read()
                mime_type = "application/pdf"
            context_sections.append("### Full Document Binary: Attached as native multimodal PDF.")
        except Exception as e:
            logger.warning(f"Could not read PDF binary at '{paper.original_pdf_path}': {e}")

    if not has_md and not pdf_bytes and paper.abstract and paper.abstract.strip():
        context_sections.append(f"### Abstract:\n{paper.abstract.strip()}")

    # 3. SLR Screening Pipeline Results (Only if evaluated or criteria present)
    screening_lines = []
    if paper.screening_status and paper.screening_status != 'pending':
        screening_lines.append(f"- Status: {paper.screening_status}")
    if paper.screening_reasoning and paper.screening_reasoning.strip():
        screening_lines.append(f"- Reasoning: {paper.screening_reasoning.strip()}")

    crit_acc = workspace.get_full_text_acceptance_criteria() or workspace.get_abstract_acceptance_criteria()
    if crit_acc and crit_acc.strip():
        screening_lines.append(f"- Workspace Acceptance Criteria: {crit_acc.strip()}")

    crit_rej = workspace.get_full_text_rejection_criteria() or workspace.get_abstract_rejection_criteria()
    if crit_rej and crit_rej.strip():
        screening_lines.append(f"- Workspace Rejection Criteria: {crit_rej.strip()}")

    if screening_lines:
        context_sections.append("### SLR Screening Evaluation\n" + "\n".join(screening_lines))

    # 4. Extracted Parameters & Claims Matrix (Only if extractions exist)
    extractions = Extraction.objects.filter(paper=paper).select_related('extraction_definition')
    if extractions.exists():
        ext_lines = ["### Extracted Research Parameters & Evidence:"]
        for ext in extractions:
            def_name = ext.extraction_definition.name if ext.extraction_definition else ext.category
            ext_lines.append(f"#### Definition: {def_name}")
            ext_lines.append(f"- Fields Data: {json.dumps(ext.fields_data, indent=2)}")
            if ext.validation_status and ext.validation_status != 'pending':
                ext_lines.append(f"- Validation Status: {ext.validation_status} (HITL Validated: {ext.is_hitl_validated})")
        context_sections.append("\n".join(ext_lines))

    # 5. Composite Metrics & Signal Score (Only if score, details, or metrics exist)
    metrics = PaperMetric.objects.filter(paper=paper)
    metrics_lines = []
    if paper.signal_score is not None:
        metrics_lines.append(f"- Composite Signal Score: {paper.signal_score}")
    if paper.signal_score_details:
        metrics_lines.append(f"- Signal Score Calculation Details: {json.dumps(paper.signal_score_details, indent=2)}")
    if workspace.signal_score_code and (paper.signal_score is not None or metrics.exists()):
        metrics_lines.append(f"- Workspace Signal Score Formula:\n```python\n{workspace.signal_score_code}\n```")
    for m in metrics:
        if m.metrics_data:
            metrics_lines.append(f"- Run Metrics: {json.dumps(m.metrics_data, indent=2)}")

    if metrics_lines:
        context_sections.append("### Computed Quality & Signal Metrics:\n" + "\n".join(metrics_lines))

    full_context_text = "\n\n".join(context_sections)
    return full_context_text, pdf_bytes, mime_type

from .verifier import verify_citations_against_source


def extract_visual_citations_from_response(raw_text: str) -> tuple[str, list[dict]]:
    """
    Extracts structured visual citations (page, box_2d, label, quote) from the LLM completion.
    Supports embedded JSON citation blocks, XML-style tags, and markdown references (e.g. [Page 4, Fig. 2]).
    """
    if not raw_text:
        return "", []

    visual_citations = []
    cleaned_text = raw_text

    # 1. Check for structured ```json:citations ... ``` block
    if "```json:citations" in raw_text:
        try:
            parts = raw_text.split("```json:citations")
            cleaned_text = parts[0].strip()
            cit_json = parts[1].split("```")[0].strip()
            visual_citations = json.loads(cit_json)
        except Exception:
            pass

    # 2. Check for inline bracketed visual references like [Page 3, Fig. 2b, quote: "..."]
    if not visual_citations:
        pattern = re.compile(
            r'\[(?:Page|Strona)\s*(?P<page>\d+)'
            r'(?:,\s*(?P<kind>Figure|Fig\.|Table|Tab\.|Rysunek)\s*(?P<num>[\w\.\d]+))?'
            r'(?:,\s*quote:\s*["\'](?P<quote>[^"\']+)["\'])?\]',
            re.IGNORECASE
        )
        for match in pattern.finditer(raw_text):
            page_num = int(match.group('page')) if match.group('page') else 1
            kind = match.group('kind')
            num = match.group('num')
            label = f"{kind} {num}".strip() if kind and num else f"Page {page_num}"
            quote = match.group('quote') or ""
            visual_citations.append({
                "page": page_num,
                "label": label,
                "quote": quote,
                "box_2d": None
            })

    # 3. Check for explicitly quoted claims in text <quote>...</quote>
    quotes = re.findall(r'<quote>(.*?)</quote>', raw_text, re.DOTALL | re.IGNORECASE)
    for q in quotes:
        if not any(c.get("quote") == q.strip() for c in visual_citations):
            visual_citations.append({
                "page": 1,
                "label": "Direct Source Quote",
                "quote": q.strip(),
                "box_2d": None
            })

    return cleaned_text, visual_citations


def update_hierarchical_session_summary(session: PaperChatSession, history_messages):
    """
    Compresses older conversation turns into a high-level scientific memorandum on session.summary.
    """
    count = history_messages.count()
    if count < 4:
        return

    older_turns = list(history_messages[:count - 2])
    summary_lines = []
    if session.summary:
        summary_lines.append(session.summary)

    for turn in older_turns:
        if turn.question and turn.message:
            q_snippet = turn.question[:80]
            ans_snippet = turn.message[:140].replace('\n', ' ')
            summary_lines.append(f"- User inquired: '{q_snippet}' -> Established: '{ans_snippet}...'")

    if summary_lines:
        session.summary = "\n".join(summary_lines[-10:])
        session.save(update_fields=['summary', 'updated_at'])


def execute_paper_chat_logic(message: PaperChatMessage) -> dict:
    """
    Executes state-of-the-art LLM generation for a PaperChatMessage:
    1. Multi-modal full context assembly.
    2. Hierarchical session summarization.
    3. Deep Thinking reasoning mode (if requested).
    4. Visual Grounding parsing (page numbers, figure/table references, bounding boxes).
    5. Deterministic Fact-Checking & Hallucination Guard verification.
    """
    session = message.session
    paper = session.paper
    workspace = session.workspace

    message.status = 'processing'
    message.save(update_fields=['status'])

    try:
        # 1. Build complete document context
        context_text, pdf_bytes, mime_type = build_paper_context(paper)

        # 2. Build conversation history with Hierarchical Summarization
        history_messages = session.messages.filter(
            created_at__lt=message.created_at,
            status='completed'
        ).order_by('created_at')

        # Update session summary if message thread is long
        if history_messages.count() >= 4:
            update_hierarchical_session_summary(session, history_messages)

        history_dialogue = []
        if session.summary:
            history_dialogue.append(f"### Previous Conversation Scientific Summary:\n{session.summary}\n")

        # Pass only the last 2-3 turns verbatim
        recent_turns = history_messages[max(0, history_messages.count() - 3):]
        for prev in recent_turns:
            if prev.question:
                history_dialogue.append(f"User: {prev.question}")
            if prev.message:
                history_dialogue.append(f"Assistant: {prev.message}")

        history_block = ""
        if history_dialogue:
            history_block = "### Conversation Dialogue:\n" + "\n".join(history_dialogue) + "\n\n"

        # 3. Configure System Prompt & Deep Thinking Instructions
        deep_thinking_active = bool(getattr(message, 'deep_thinking', False))

        system_instruction = (
            "You are an expert AI Research Analyst and Deep-Tech Scientific Advisor for the Schwarz Research Intelligence platform. "
            "You are discussing an academic paper with a researcher.\n"
            "You have access to the complete context of the paper, including its layout text/PDF, screening decision rationale, "
            "all dynamic extracted parameters, confidence scores, and computed signal scores.\n\n"
            "Grounding & Visual Citation Guidelines:\n"
            "1. Answer questions factually, thoroughly, and with deep scientific precision.\n"
            "2. Whenever citing facts, measurements, or claims, enclose verbatim quotes in <quote>exact quote from source</quote> "
            "or reference the visual location like [Page X, Figure Y].\n"
            "3. If visual citations are available, include page numbers, figure/table labels, and approximate bounding boxes.\n"
            "4. If asked why the paper was accepted/rejected or scored with a specific value, explain the criteria and mathematical formula.\n"
            "5. Structure your response clearly using Markdown formatting."
        )

        if deep_thinking_active:
            system_instruction += (
                "\n\n[DEEP SCIENTIFIC REASONING MODE ACTIVATED]\n"
                "Execute rigorous step-by-step mathematical, thermodynamic, or algorithmic derivation before stating final conclusions. "
                "Verify dimensional consistency in equations and benchmark numbers."
            )

        user_prompt = f"""{context_text}

{history_block}### Current Question from Researcher:
{message.question}

Please provide a detailed, accurate response grounded strictly in the source document with exact citations."""

        # 4. Call LLM Provider
        provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
        model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash') or 'google/gemini-3.7-flash'

        provider = get_llm_provider(provider_name)
        llm_response = provider.generate(
            prompt=user_prompt,
            model=model_name,
            file_bytes=pdf_bytes,
            mime_type=mime_type,
            system_instruction=system_instruction,
            temperature=0.1 if deep_thinking_active else 0.2,
            max_tokens=8192 if deep_thinking_active else 4096,
            return_usage=True,
        )

        if isinstance(llm_response, tuple) and len(llm_response) == 2:
            answer_raw, usage = llm_response
            tokens_in = usage.get("prompt_tokens", 0) or 0
            tokens_out = usage.get("candidates_tokens", 0) or 0
        else:
            answer_raw = str(llm_response) if llm_response else ""
            tokens_in = 0
            tokens_out = 0

        if not isinstance(answer_raw, str):
            answer_raw = json.dumps(answer_raw, indent=2) if answer_raw else ""

        # 5. Extract Visual Grounding Citations
        cleaned_answer, parsed_visual_citations = extract_visual_citations_from_response(answer_raw)
        citations_list = getattr(llm_response, 'citations', []) or []

        # 6. Deterministic Fact-Checking & Hallucination Guard
        verified_visual_cits, guard_summary = verify_citations_against_source(
            source_text=context_text,
            visual_citations=parsed_visual_citations,
            answer_text=cleaned_answer
        )

        # 7. Record token and cost accounting on workspace
        cost = workspace.record_token_usage(tokens_in, tokens_out, model_name=model_name)

        # 8. Update message in DB
        message.message = cleaned_answer
        message.tokens_in = tokens_in
        message.tokens_out = tokens_out
        message.usd_cost = cost
        message.status = 'completed'
        message.completed_at = timezone.now()
        message.citations = citations_list
        message.visual_citations = verified_visual_cits
        message.hallucination_guard = guard_summary
        message.save(update_fields=[
            'message', 'tokens_in', 'tokens_out', 'usd_cost', 'status',
            'completed_at', 'citations', 'visual_citations', 'hallucination_guard'
        ])

        # 9. Update session title if first turn
        if session.messages.count() <= 2 and (session.title == "Paper Discussion" or not session.title):
            session.title = (message.question[:60] + "...") if len(message.question) > 60 else message.question
            session.save(update_fields=['title', 'updated_at'])

        return {
            "status": "completed",
            "message_id": str(message.id),
            "session_id": str(session.id),
            "paper_id": str(paper.id),
            "paper_title": paper.title,
            "answer": cleaned_answer,
            "citations": citations_list,
            "visual_citations": verified_visual_cits,
            "hallucination_guard": guard_summary,
            "deep_thinking": deep_thinking_active,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "usd_cost": float(cost),
        }

    except Exception as ex:
        logger.error(f"Paper chat execution failed for message '{message.id}': {ex}", exc_info=True)
        message.status = 'failed'
        message.error_message = str(ex)
        message.completed_at = timezone.now()
        message.save(update_fields=['status', 'error_message', 'completed_at'])
        return {
            "status": "failed",
            "message_id": str(message.id),
            "session_id": str(session.id),
            "error": str(ex),
        }
