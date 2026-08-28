import logging
import json
from typing import Generator
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
from .cache_manager import GeminiContextCacheManager

logger = logging.getLogger(__name__)


class PaperChatEngine:
    """
    Core OOP domain orchestrator for interactive scientific paper Q&A.
    Coordinates context building, memory summarization, deep thinking prompts,
    Gemini server-side context caching, streaming (SSE), visual grounding extraction,
    fact checking, and token / cost accounting.
    """

    def __init__(
        self,
        context_builder: PaperContextBuilder = None,
        session_summarizer: HierarchicalSessionSummarizer = None,
        summarizer: HierarchicalSessionSummarizer = None,
        citation_extractor: VisualCitationExtractor = None,
        fact_checker: CitationFactChecker = None,
        cache_manager: GeminiContextCacheManager = None
    ):
        self.context_builder = context_builder or PaperContextBuilder()
        self.session_summarizer = session_summarizer or summarizer or HierarchicalSessionSummarizer()
        self.citation_extractor = citation_extractor or VisualCitationExtractor()
        self.fact_checker = fact_checker or CitationFactChecker()
        self.cache_manager = cache_manager or GeminiContextCacheManager()

    def execute(self, message: PaperChatMessage) -> dict:
        """
        Executes generation for a single PaperChatMessage turn synchronously.

        Returns:
            dict with answer, citations, visual citations, grounding audit, tokens, and cost.
        """
        session = message.session
        paper = session.paper
        workspace = session.workspace

        try:
            message.status = 'processing'
            message.save(update_fields=['status'])

            # 1. Build structured context
            context_text, pdf_bytes, mime_type = self.context_builder.build(paper, workspace=workspace)

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
                "Your objective is to answer questions regarding the attached academic paper or research workspace with utmost scientific precision, rigor, and clarity.\n\n"
                "RULES & CONSTRAINTS:\n"
                "1. Base your assertions strictly on the provided paper document, screening decisions, and extracted parameters.\n"
                "2. When citing specific figures, tables, formulas, or pages, provide visual references in this format: [Page X, Fig Y, box_2d: [ymin, xmin, ymax, xmax], quote: \"exact evidence sentence\"].\n"
                "3. If deep thinking is requested, show your reasoning and cross-check multiple sections of the paper before delivering your final conclusion.\n"
                "4. If information is not in the document, explicitly state that it is not covered."
            )

            provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
            provider = get_llm_provider(provider_name)

            # 4. Check / Create Gemini Server-Side Context Cache
            cached_content_name = self.cache_manager.get_or_create_cache(
                session=session,
                paper=paper,
                workspace=workspace,
                context_text=context_text,
                pdf_bytes=pdf_bytes,
                mime_type=mime_type,
                system_instruction=system_instruction,
                provider=provider
            )

            # If cached on server, omit raw context from inline prompt to save tokens
            prompt_context = "" if cached_content_name else context_text
            prompt_pdf = None if cached_content_name else pdf_bytes
            prompt_mime = None if cached_content_name else mime_type

            prompt = self._assemble_prompt(prompt_context, history_text, message.question, deep_thinking_active)

            # 5. Generate LLM Response
            answer_raw, citations_list, tokens_in, tokens_out, thought_process = self._call_llm(
                workspace=workspace,
                prompt=prompt,
                pdf_bytes=prompt_pdf,
                mime_type=prompt_mime,
                system_instruction=system_instruction if not cached_content_name else None,
                deep_thinking_active=deep_thinking_active,
                cached_content=cached_content_name
            )

            # 6. Extract Visual Grounding Citations
            cleaned_answer, parsed_visual_citations = self.citation_extractor.extract(answer_raw)

            # 7. Fact-Checking & Hallucination Guard
            verified_visual_cits, guard_summary = self.fact_checker.verify(
                source_text=context_text,
                visual_citations=parsed_visual_citations,
                answer_text=cleaned_answer
            )

            # 8. Record token usage and cost accounting on Workspace & Session
            model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash') or 'google/gemini-3.7-flash'
            total_tokens = (tokens_in or 0) + (tokens_out or 0)
            cost = workspace.record_token_usage(
                tokens_in,
                tokens_out,
                model_name=model_name
            )

            session.record_message_cost(tokens_in, tokens_out, cost)

            message.message = cleaned_answer
            message.thinking_process = thought_process or ""
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
                'message', 'thinking_process', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost',
                'llm_model', 'status', 'completed_at', 'citations', 'visual_citations', 'hallucination_guard'
            ])

            # 9. Update session title if first turn
            if session.messages.count() <= 2 and (session.title == "Paper Discussion" or not session.title):
                session.title = (message.question[:60] + "...") if len(message.question) > 60 else message.question
                session.save(update_fields=['title', 'updated_at'])

            return {
                "status": "completed",
                "message_id": str(message.id),
                "session_id": str(session.id),
                "paper_id": str(paper.id) if paper else None,
                "paper_title": paper.title if paper else None,
                "answer": cleaned_answer,
                "thinking_process": thought_process or "",
                "citations": citations_list,
                "visual_citations": verified_visual_cits,
                "hallucination_guard": guard_summary,
                "deep_thinking": deep_thinking_active,
                "llm_model": model_name,
                "cached_content": cached_content_name,
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

    def execute_stream(self, message: PaperChatMessage) -> Generator[str, None, None]:
        """
        Executes streaming LLM generation for a PaperChatMessage turn, yielding Server-Sent Events (SSE).
        Format per chunk: 'event: <event_name>\ndata: <json_payload>\n\n'
        """
        session = message.session
        paper = session.paper
        workspace = session.workspace

        try:
            message.status = 'processing'
            message.save(update_fields=['status'])

            # Initial metadata SSE event
            yield f"event: metadata\ndata: {json.dumps({'message_id': str(message.id), 'session_id': str(session.id), 'status': 'processing'})}\n\n"

            # 1. Build context & history
            context_text, pdf_bytes, mime_type = self.context_builder.build(paper, workspace=workspace)
            history_messages = list(
                session.messages.filter(status='completed').exclude(id=message.id).order_by('created_at')
            )
            self.session_summarizer.compress_and_update(session, history_messages)
            history_text = self.session_summarizer.build_history_block(session, history_messages)

            deep_thinking_active = getattr(message, 'deep_thinking', False)
            system_instruction = (
                "You are an expert scientific research assistant and deep-tech reviewer within the Schwarz Research Intelligence platform.\n"
                "Your objective is to answer questions regarding the attached academic paper or research workspace with utmost scientific precision, rigor, and clarity.\n\n"
                "RULES & CONSTRAINTS:\n"
                "1. Base your assertions strictly on the provided paper document, screening decisions, and extracted parameters.\n"
                "2. When citing specific figures, tables, formulas, or pages, provide visual references in this format: [Page X, Fig Y, box_2d: [ymin, xmin, ymax, xmax], quote: \"exact evidence sentence\"].\n"
                "3. If deep thinking is requested, show your reasoning and cross-check multiple sections of the paper before delivering your final conclusion.\n"
                "4. If information is not in the document, explicitly state that it is not covered."
            )

            provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
            model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash') or 'google/gemini-3.7-flash'
            provider = get_llm_provider(provider_name)

            # 2. Context Cache
            cached_content_name = self.cache_manager.get_or_create_cache(
                session=session,
                paper=paper,
                workspace=workspace,
                context_text=context_text,
                pdf_bytes=pdf_bytes,
                mime_type=mime_type,
                system_instruction=system_instruction,
                provider=provider
            )

            prompt_context = "" if cached_content_name else context_text
            prompt_pdf = None if cached_content_name else pdf_bytes
            prompt_mime = None if cached_content_name else mime_type

            prompt = self._assemble_prompt(prompt_context, history_text, message.question, deep_thinking_active)

            accumulated_text = []
            accumulated_thoughts = []
            final_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}

            if hasattr(provider, 'generate_stream'):
                for chunk_text, usage in provider.generate_stream(
                    prompt=prompt,
                    model=model_name,
                    file_bytes=prompt_pdf,
                    mime_type=prompt_mime,
                    system_instruction=system_instruction if not cached_content_name else None,
                    temperature=0.1 if deep_thinking_active else 0.2,
                    max_tokens=8192 if deep_thinking_active else 4096,
                    cached_content=cached_content_name,
                    deep_thinking=deep_thinking_active,
                    include_thoughts=deep_thinking_active
                ):
                    if usage and isinstance(usage, dict) and usage.get("thought"):
                        thought_chunk = usage["thought"]
                        accumulated_thoughts.append(thought_chunk)
                        yield f"event: thought\ndata: {json.dumps({'thought': thought_chunk})}\n\n"
                    if chunk_text:
                        accumulated_text.append(chunk_text)
                        yield f"event: delta\ndata: {json.dumps({'delta': chunk_text})}\n\n"
                    if usage:
                        final_usage = usage
            else:
                # Fallback to single-pass generation
                resp_raw = provider.generate(
                    prompt=prompt,
                    model=model_name,
                    file_bytes=prompt_pdf,
                    mime_type=prompt_mime,
                    system_instruction=system_instruction if not cached_content_name else None,
                    deep_thinking=deep_thinking_active,
                    include_thoughts=deep_thinking_active
                )
                accumulated_text.append(str(resp_raw))
                yield f"event: delta\ndata: {json.dumps({'delta': str(resp_raw)})}\n\n"

            full_answer = "".join(accumulated_text)
            full_thoughts = "".join(accumulated_thoughts)
            cleaned_answer, parsed_visual_citations = self.citation_extractor.extract(full_answer)

            if parsed_visual_citations:
                yield f"event: visual_citations\ndata: {json.dumps({'visual_citations': parsed_visual_citations})}\n\n"

            # Fact Check
            verified_visual_cits, guard_summary = self.fact_checker.verify(
                source_text=context_text,
                visual_citations=parsed_visual_citations,
                answer_text=cleaned_answer
            )
            yield f"event: fact_check\ndata: {json.dumps({'hallucination_guard': guard_summary})}\n\n"

            # Cost & Usage
            tokens_in = final_usage.get("prompt_tokens", 0) or 0
            tokens_out = final_usage.get("candidates_tokens", 0) or 0
            total_tokens = final_usage.get("total_tokens", tokens_in + tokens_out)
            cost = workspace.record_token_usage(tokens_in, tokens_out, model_name=model_name)
            session.record_message_cost(tokens_in, tokens_out, cost)

            yield f"event: usage\ndata: {json.dumps({'tokens_in': tokens_in, 'tokens_out': tokens_out, 'total_tokens': total_tokens, 'usd_cost': float(cost)})}\n\n"

            # Persist message
            message.message = cleaned_answer
            message.thinking_process = full_thoughts
            message.tokens_in = tokens_in
            message.tokens_out = tokens_out
            message.total_tokens = total_tokens
            message.usd_cost = cost
            message.llm_model = model_name
            message.status = 'completed'
            message.completed_at = timezone.now()
            message.visual_citations = verified_visual_cits
            message.hallucination_guard = guard_summary
            message.save(update_fields=[
                'message', 'thinking_process', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost',
                'llm_model', 'status', 'completed_at', 'visual_citations', 'hallucination_guard'
            ])

            yield f"event: done\ndata: {json.dumps({'status': 'completed', 'message_id': str(message.id)})}\n\n"

        except Exception as ex:
            logger.error(f"Streaming failed for message '{message.id}': {ex}", exc_info=True)
            message.status = 'failed'
            message.error_message = str(ex)
            message.completed_at = timezone.now()
            message.save(update_fields=['status', 'error_message', 'completed_at'])
            yield f"event: error\ndata: {json.dumps({'error': str(ex)})}\n\n"

    def _assemble_prompt(self, context_text: str, history_text: str, question: str, deep_thinking_active: bool) -> str:
        """Assembles the user prompt, context block, and conversation history."""
        prompt_parts = []

        if context_text:
            prompt_parts.append(f"## ACADEMIC CONTEXT & METRICS\n{context_text}")

        if history_text:
            prompt_parts.append(f"## CONVERSATION MEMORY\n{history_text}")

        if deep_thinking_active:
            prompt_parts.append(
                "## DEEP SCIENTIFIC REASONING DIRECTIVE\n"
                "Please perform deep chain-of-thought analysis. Formulate hypotheses, evaluate empirical evidence provided in document text/figures, verify numerical claims, and synthesize a structured response with exact quotes and visual references."
            )

        prompt_parts.append(f"## USER QUESTION\n{question}")
        return "\n\n".join(prompt_parts)

    def _call_llm(
        self,
        workspace,
        prompt: str,
        pdf_bytes: bytes | None,
        mime_type: str | None,
        system_instruction: str | None,
        deep_thinking_active: bool,
        cached_content: str | None = None
    ) -> tuple[str, list, int, int, str]:
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
            cached_content=cached_content,
            deep_thinking=deep_thinking_active,
            include_thoughts=deep_thinking_active,
            return_usage=True,
        )

        thought_text = ""
        if isinstance(llm_response, tuple) and len(llm_response) == 2:
            answer_raw, usage = llm_response
            tokens_in = usage.get("prompt_tokens", 0) or 0
            tokens_out = usage.get("candidates_tokens", 0) or 0
            thought_text = usage.get("thought_process", "") or ""
        else:
            answer_raw = str(llm_response) if llm_response else ""
            tokens_in = 0
            tokens_out = 0

        if not isinstance(answer_raw, str):
            answer_raw = json.dumps(answer_raw, indent=2) if answer_raw else ""

        citations_list = getattr(llm_response, 'citations', []) or []
        return answer_raw, citations_list, tokens_in, tokens_out, thought_text
