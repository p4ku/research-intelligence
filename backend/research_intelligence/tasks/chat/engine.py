import json
import logging
from django.utils import timezone

from research_intelligence.models import (
    Paper,
    PaperChatSession,
    PaperChatMessage,
)
from research_intelligence.llm_providers import get_llm_provider
from .context_builder import PaperContextBuilder
from .summarizer import HierarchicalSessionSummarizer
from .citations import VisualCitationExtractor
from .verifier import CitationFactChecker

logger = logging.getLogger(__name__)


class PaperChatEngine:
    """
    State-of-the-Art Interactive Paper Intelligence Engine.
    Orchestrates:
    - Clean multimodal context building.
    - Hierarchical session summarization.
    - Deep scientific reasoning (thinking budget).
    - Visual citation grounding.
    - Deterministic fact-checking & hallucination guards.
    """

    def __init__(
        self,
        context_builder: PaperContextBuilder | None = None,
        summarizer: HierarchicalSessionSummarizer | None = None,
        citation_extractor: VisualCitationExtractor | None = None,
        fact_checker: CitationFactChecker | None = None,
    ):
        self.context_builder = context_builder or PaperContextBuilder()
        self.summarizer = summarizer or HierarchicalSessionSummarizer()
        self.citation_extractor = citation_extractor or VisualCitationExtractor()
        self.fact_checker = fact_checker or CitationFactChecker()

    def execute(self, message: PaperChatMessage) -> dict:
        """
        Executes interactive paper Q&A for a given PaperChatMessage turn.
        """
        session = message.session
        paper = session.paper
        workspace = session.workspace

        message.status = 'processing'
        message.save(update_fields=['status'])

        try:
            # 1. Build document context
            context_text, pdf_bytes, mime_type = self.context_builder.build(paper)

            # 2. Build conversation history & hierarchical summary
            history_messages = session.messages.filter(
                created_at__lt=message.created_at,
                status='completed'
            ).order_by('created_at')

            self.summarizer.compress_and_update(session, history_messages)
            history_block = self.summarizer.build_history_block(session, history_messages)

            # 3. Prepare system & user prompts
            deep_thinking_active = bool(getattr(message, 'deep_thinking', False))
            system_instruction = self._prepare_system_instruction(deep_thinking_active)
            user_prompt = self._build_user_prompt(context_text, history_block, message.question)

            # 4. Invoke LLM provider
            answer_raw, citations_list, tokens_in, tokens_out = self._invoke_llm(
                workspace=workspace,
                prompt=user_prompt,
                pdf_bytes=pdf_bytes,
                mime_type=mime_type,
                system_instruction=system_instruction,
                deep_thinking_active=deep_thinking_active
            )

            # 5. Extract Visual Grounding Citations
            cleaned_answer, parsed_visual_citations = self.citation_extractor.extract(answer_raw)

            # 6. Fact-Checking & Hallucination Guard
            verified_visual_cits, guard_summary = self.fact_checker.verify(
                source_text=context_text,
                visual_citations=parsed_visual_citations,
                answer_text=cleaned_answer
            )

            # 7. Record token usage and update message in DB
            cost = workspace.record_token_usage(
                tokens_in,
                tokens_out,
                model_name=getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash')
            )

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

            # 8. Update session title if first turn
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

    def _prepare_system_instruction(self, deep_thinking_active: bool) -> str:
        instruction = (
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
            instruction += (
                "\n\n[DEEP SCIENTIFIC REASONING MODE ACTIVATED]\n"
                "Execute rigorous step-by-step mathematical, thermodynamic, or algorithmic derivation before stating final conclusions. "
                "Verify dimensional consistency in equations and benchmark numbers."
            )
        return instruction

    def _build_user_prompt(self, context_text: str, history_block: str, question: str) -> str:
        return f"""{context_text}

{history_block}### Current Question from Researcher:
{question}

Please provide a detailed, accurate response grounded strictly in the source document with exact citations."""

    def _invoke_llm(
        self,
        workspace,
        prompt: str,
        pdf_bytes: bytes | None,
        mime_type: str | None,
        system_instruction: str,
        deep_thinking_active: bool
    ) -> tuple[str, list, int, int]:
        provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
        model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash') or 'google/gemini-3.7-flash'

        provider = get_llm_provider(provider_name)
        llm_response = provider.generate(
            prompt=prompt,
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

        citations_list = getattr(llm_response, 'citations', []) or []
        return answer_raw, citations_list, tokens_in, tokens_out
