import logging
import json
from django.utils import timezone

from chat.models import (
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
    Core OOP domain orchestrator for interactive scientific paper Q&A.
    Coordinates context building, memory summarization, deep thinking prompts,
    LLM API generation, visual grounding extraction, fact checking, and token / cost accounting.
    """

    def __init__(
        self,
        context_builder: PaperContextBuilder = None,
        session_summarizer: HierarchicalSessionSummarizer = None,
        summarizer: HierarchicalSessionSummarizer = None,
        citation_extractor: VisualCitationExtractor = None,
        fact_checker: CitationFactChecker = None
    ):
        self.context_builder = context_builder or PaperContextBuilder()
        self.session_summarizer = session_summarizer or summarizer or HierarchicalSessionSummarizer()
        self.citation_extractor = citation_extractor or VisualCitationExtractor()
        self.fact_checker = fact_checker or CitationFactChecker()

    def execute(self, message: PaperChatMessage) -> dict:
        """
        Executes generation for a single PaperChatMessage turn.

        Returns:
            dict with answer, citations, visual citations, grounding audit, tokens, and cost.
        """
        session = message.session
        paper = session.paper
        workspace = session.workspace

        try:
            message.status = 'processing'
            message.save(update_fields=['status'])

            # 1. Build structured paper context
            context_text, pdf_bytes, mime_type = self.context_builder.build(paper)

            # 2. Build multi-turn history & update hierarchical session summary
            history_messages = list(
                session.messages.filter(status='completed')
                .exclude(id=message.id)
                .order_by('created_at')
            )
            self.session_summarizer.compress_and_update(session, history_messages)
            history_text = self.session_summarizer.build_history_block(session, history_messages)

            # 3. Assemble System Prompt & Deep Thinking Instructions
            deep_thinking_active = getattr(message, 'deep_thinking', False)
            system_instruction = (
                "You are an expert scientific research assistant and deep-tech reviewer within the Schwarz Research Intelligence platform.\n"
                "Your objective is to answer questions regarding the attached academic paper with utmost scientific precision, rigor, and clarity.\n\n"
                "RULES & CONSTRAINTS:\n"
                "1. Base your assertions strictly on the provided paper document, screening decisions, and extracted parameters.\n"
                "2. When citing specific figures, tables, formulas, or pages, provide visual references in this format: [Page X, Fig Y, box_2d: [ymin, xmin, ymax, xmax], quote: \"exact evidence sentence\"].\n"
                "3. If deep thinking is requested, show your reasoning and cross-check multiple sections of the paper before delivering your final conclusion.\n"
                "4. If information is not in the paper, explicitly state that it is not covered."
            )

            prompt = self._assemble_prompt(context_text, history_text, message.question, deep_thinking_active)

            # 4. Generate LLM Response
            answer_raw, citations_list, tokens_in, tokens_out = self._call_llm(
                workspace=workspace,
                prompt=prompt,
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

            # 7. Record token usage and cost accounting on Workspace & Session
            model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash') or 'google/gemini-3.7-flash'
            total_tokens = (tokens_in or 0) + (tokens_out or 0)
            cost = workspace.record_token_usage(
                tokens_in,
                tokens_out,
                model_name=model_name
            )

            session.record_message_cost(tokens_in, tokens_out, cost)

            message.message = cleaned_answer
            message.tokens_in = tokens_in
            message.tokens_out = tokens_out
            message.total_tokens = total_tokens
            message.usd_cost = cost
            message.llm_model = model_name
            message.status = 'completed'
            message.completed_at = timezone.now()
            message.citations = citations_list
            message.visual_citations = verified_visual_cits
            message.hallucination_guard = guard_summary
            message.save(update_fields=[
                'message', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost',
                'llm_model', 'status', 'completed_at', 'citations', 'visual_citations', 'hallucination_guard'
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
                "llm_model": model_name,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "total_tokens": total_tokens,
                "usd_cost": float(cost),
                "session_total_tokens": session.total_tokens,
                "session_total_usd_cost": float(session.total_usd_cost),
                "workspace_monthly_tokens": workspace.tokens_consumed_this_month,
                "workspace_monthly_usd": float(workspace.usd_spent_this_month),
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

    def _assemble_prompt(self, context_text: str, history_text: str, question: str, deep_thinking_active: bool) -> str:
        """Assembles the user prompt, context block, and conversation history."""
        prompt_parts = []

        if context_text:
            prompt_parts.append(f"## ACADEMIC PAPER CONTEXT & METRICS\n{context_text}")

        if history_text:
            prompt_parts.append(f"## CONVERSATION MEMORY\n{history_text}")

        if deep_thinking_active:
            prompt_parts.append(
                "## DEEP SCIENTIFIC REASONING DIRECTIVE\n"
                "Please perform deep chain-of-thought analysis. Formulate hypotheses, evaluate the empirical evidence provided in the paper text/figures, verify numerical claims, and synthesize a structured response with exact quotes and visual references."
            )

        prompt_parts.append(f"## USER QUESTION\n{question}")
        return "\n\n".join(prompt_parts)

    def _call_llm(
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
