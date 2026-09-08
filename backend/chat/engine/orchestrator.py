import logging
import json
from dataclasses import dataclass, field
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

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'google/gemini-3.8-flash'

SYSTEM_INSTRUCTION = (
    "You are the research assistant inside Schwarz Research Intelligence, a platform where researchers run "
    "systematic literature reviews over deep-tech papers. You answer questions about one paper, or about a "
    "workspace of papers, for a researcher who will act on the answer without re-reading the paper themselves.\n\n"
    "What you are given, and where each part comes from:\n"
    "- PAPER DOCUMENT: the paper's metadata and its full text (OCR markdown), or the PDF itself. "
    "This is the only source for claims about what the paper says.\n"
    "- SCREENING, EXTRACTIONS & METRICS: the platform's own annotations - a screening decision with its rationale, "
    "extracted parameters, and a computed signal score with the formula behind it. These are pipeline output, not "
    "the authors' claims. When the researcher asks why a paper was accepted, rejected or scored, answer from this "
    "section and say that it is the platform's assessment.\n"
    "- CONVERSATION MEMORY: earlier turns of this conversation; older ones are abridged.\n\n"
    "Ground every claim in those sections. If the answer is not in them, say so instead of filling the gap from "
    "general knowledge; if you add background from outside the paper, label it as such.\n"
    "When you point at a figure, table, equation or passage, use this marker so the interface can turn it into a "
    "chip: [Page X, Fig Y, quote: \"exact sentence from the document\"]. Include \"Page X\" only when the document "
    "text itself shows page numbers; otherwise leave it out and write [Fig Y, quote: \"...\"] or just "
    "[quote: \"...\"]. The quote must be copied verbatim: quoted text is checked against the document and "
    "is flagged to the researcher when it does not match.\n"
    "Answer in the language the question was asked in."
)

# Page numbers and bounding boxes only mean something when the model can see
# the pages, i.e. when the PDF itself is attached. The OCR markdown carries no
# page boundaries, so there both would be invented.
PDF_CITATION_ADDENDUM = (
    "The PDF is attached, so every marker can carry its page number and a bounding box: "
    "[Page X, Fig Y, box_2d: [ymin, xmin, ymax, xmax], quote: \"...\"], coordinates normalised to 0-1000."
)


@dataclass
class PreparedTurn:
    """Everything a single chat turn needs, assembled once and shared by the sync and streaming paths."""
    prompt: str
    system_instruction: str
    source_text: str
    pdf_bytes: bytes | None
    mime_type: str | None
    provider: object
    model_name: str
    reasoning_effort: str | None
    deep_thinking: bool


@dataclass
class TurnUsage:
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_tokens: int = 0
    thought_process: str = ""
    citations: list = field(default_factory=list)

    def absorb(self, usage: dict | None) -> None:
        """Folds a provider usage dict in; later non-zero counts win, thoughts accumulate."""
        if not usage or not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "candidates_tokens", "cached_tokens"):
            value = usage.get(key) or 0
            if value > 0:
                setattr(self, key, value)
        if usage.get("thought_process"):
            self.thought_process = usage["thought_process"]


class PaperChatEngine:
    """
    Core OOP domain orchestrator for interactive scientific paper Q&A.
    Coordinates context building, memory summarization, deep thinking prompts,
    streaming (SSE), visual grounding extraction, fact checking, and token / cost accounting.

    Prompts are ordered system → document → annotations → history → question so the
    large, immutable paper text is a stable prefix that Gemini's implicit cache can reuse.
    """

    def __init__(
        self,
        context_builder: PaperContextBuilder = None,
        session_summarizer: HierarchicalSessionSummarizer = None,
        summarizer: HierarchicalSessionSummarizer = None,
        citation_extractor: VisualCitationExtractor = None,
        fact_checker: CitationFactChecker = None,
    ):
        self.context_builder = context_builder or PaperContextBuilder()
        self.session_summarizer = session_summarizer or summarizer or HierarchicalSessionSummarizer()
        self.citation_extractor = citation_extractor or VisualCitationExtractor()
        self.fact_checker = fact_checker or CitationFactChecker()

    # ------------------------------------------------------------------ public

    def execute(self, message: PaperChatMessage) -> dict:
        """
        Executes generation for a single PaperChatMessage turn synchronously.

        Returns:
            dict with answer, citations, visual citations, grounding audit, tokens, and cost.
        """
        quota_error = self._check_quota(message)
        if quota_error:
            return self._fail(message, quota_error, log=False)

        try:
            message.status = 'processing'
            message.save(update_fields=['status'])

            turn = self._prepare(message)
            answer_raw, usage = self._generate(turn)
            return self._finish(message, turn, answer_raw, usage)

        except Exception as ex:
            logger.error(f"Paper chat execution failed for message '{message.id}': {ex}", exc_info=True)
            return self._fail(message, str(ex))

    def execute_stream(self, message: PaperChatMessage) -> Generator[str, None, None]:
        """
        Executes streaming LLM generation for a PaperChatMessage turn, yielding Server-Sent Events (SSE).
        Format per chunk: 'event: <event_name>\ndata: <json_payload>\n\n'
        """
        session = message.session
        paper = session.paper

        quota_error = self._check_quota(message)
        if quota_error:
            self._fail(message, quota_error, log=False)
            yield self._sse('error', {'error': quota_error})
            return

        try:
            message.status = 'processing'
            message.save(update_fields=['status'])

            yield self._sse('metadata', {
                'message_id': str(message.id),
                'session_id': str(session.id),
                'paper_id': str(paper.id) if paper else None,
                'paper_title': paper.title if paper else None,
                'status': 'processing',
            })

            turn = self._prepare(message)
            accumulated_text = []
            usage = TurnUsage()

            if hasattr(turn.provider, 'generate_stream'):
                thoughts = []
                for chunk_text, chunk_usage in turn.provider.generate_stream(**self._generation_kwargs(turn)):
                    if chunk_usage and isinstance(chunk_usage, dict):
                        if chunk_usage.get("thought"):
                            thoughts.append(chunk_usage["thought"])
                            yield self._sse('thought', {'thought': chunk_usage["thought"]})
                        usage.absorb(chunk_usage)
                    if chunk_text:
                        accumulated_text.append(chunk_text)
                        yield self._sse('delta', {'delta': chunk_text})
                usage.thought_process = "".join(thoughts)
            else:
                # Fallback to single-pass generation
                answer_raw, usage = self._generate(turn)
                accumulated_text.append(answer_raw)
                yield self._sse('delta', {'delta': answer_raw})

            result = self._finish(message, turn, "".join(accumulated_text), usage)

            if result["visual_citations"]:
                yield self._sse('visual_citations', {'visual_citations': result["visual_citations"]})
            yield self._sse('fact_check', {'hallucination_guard': result["hallucination_guard"]})
            yield self._sse('usage', {
                'tokens_in': result["tokens_in"],
                'tokens_out': result["tokens_out"],
                'total_tokens': result["total_tokens"],
                'usd_cost': result["usd_cost"],
            })
            yield self._sse('done', {'status': 'completed', 'message_id': str(message.id)})

        except GeneratorExit:
            logger.info(f"Client disconnected during SSE stream for message '{message.id}'.")
            if message.status == 'processing':
                message.status = 'aborted'
                message.error_message = 'Client disconnected during streaming generation.'
                message.completed_at = timezone.now()
                message.save(update_fields=['status', 'error_message', 'completed_at'])
            raise

        except Exception as ex:
            logger.exception(f"Paper chat streaming failed for message '{message.id}': {ex}")
            self._fail(message, str(ex), log=False)
            yield self._sse('error', {'error': str(ex)})

    # ---------------------------------------------------------------- turn steps

    def _check_quota(self, message: PaperChatMessage) -> str | None:
        workspace = message.session.workspace
        if not workspace:
            return None
        is_exceeded, quota_reason = workspace.is_quota_exceeded()
        if is_exceeded:
            return f"Workspace monthly quota exceeded: {quota_reason}"
        return None

    def _prepare(self, message: PaperChatMessage) -> PreparedTurn:
        """Builds the prompt: immutable document first, then live annotations, memory, and the question."""
        session = message.session
        paper = session.paper
        workspace = session.workspace

        if paper:
            doc = self.context_builder.document(paper)
            document_text, pdf_bytes, mime_type = doc.text, doc.pdf_bytes, doc.mime_type
            annotations_text = self.context_builder.annotations(paper, workspace)
        else:
            document_text = self.context_builder.workspace_overview(workspace) if workspace else ""
            pdf_bytes, mime_type, annotations_text = None, None, ""

        history_messages = list(
            session.messages.filter(status='completed').exclude(id=message.id).order_by('created_at')
        )
        self.session_summarizer.compress_and_update(session, history_messages)
        history_text = self.session_summarizer.build_history_block(session, history_messages)

        deep_thinking = bool(getattr(message, 'deep_thinking', False))
        prompt = self._assemble_prompt(document_text, annotations_text, history_text, message.question, deep_thinking)

        provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
        model_name = getattr(workspace, 'screening_llm_model', DEFAULT_MODEL) or DEFAULT_MODEL
        # Same workspace knob the screening and extraction steps honour; a deep
        # turn overrides it upward, since the provider's default is already
        # "medium" and the flag has to buy more than that to mean anything.
        workspace_effort = getattr(workspace, 'reasoning_effort', None) or None
        if workspace_effort == "off":
            # A zero thinking budget is not accepted by the Gemini 3 models chat
            # runs on; "low" is the smallest level they take.
            workspace_effort = "low"
        reasoning_effort = "high" if deep_thinking else workspace_effort

        return PreparedTurn(
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION + ("\n\n" + PDF_CITATION_ADDENDUM if pdf_bytes else ""),
            source_text="\n\n".join(part for part in (document_text, annotations_text) if part),
            pdf_bytes=pdf_bytes,
            mime_type=mime_type,
            provider=get_llm_provider(provider_name),
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            deep_thinking=deep_thinking,
        )

    def _assemble_prompt(
        self,
        document_text: str,
        annotations_text: str,
        history_text: str,
        question: str,
        deep_thinking_active: bool,
    ) -> str:
        """Stable prefix (document) first; everything that changes between turns after it."""
        prompt_parts = []

        if document_text:
            prompt_parts.append(f"## PAPER DOCUMENT\n{document_text}")

        if annotations_text:
            prompt_parts.append(f"## SCREENING, EXTRACTIONS & METRICS\n{annotations_text}")

        if history_text:
            prompt_parts.append(f"## CONVERSATION MEMORY\n{history_text}")

        if deep_thinking_active:
            prompt_parts.append(
                "## DEEP SCIENTIFIC REASONING DIRECTIVE\n"
                "This turn was asked with deep thinking on. Check each numerical claim against the document's own "
                "tables and figures before stating it, and give a page/figure marker for every claim you make."
            )

        prompt_parts.append(f"## USER QUESTION\n{question}")
        return "\n\n".join(prompt_parts)

    def _generation_kwargs(self, turn: PreparedTurn) -> dict:
        return dict(
            prompt=turn.prompt,
            model=turn.model_name,
            file_bytes=turn.pdf_bytes,
            mime_type=turn.mime_type,
            system_instruction=turn.system_instruction,
            # Google's Gemini 3 guidance is the default 1.0 for reasoning-heavy
            # work, so deep turns use it. Ordinary turns keep the pre-audit 0.2
            # until a replay shows the fact-checker's verbatim-quote pass rate
            # holds at 1.0 (see PR #102 discussion).
            temperature=1.0 if turn.deep_thinking else 0.2,
            # Thinking tokens count against max_output_tokens on Gemini, so the
            # ceiling has to cover the thinking budget plus a fully cited answer.
            max_tokens=16384,
            deep_thinking=turn.deep_thinking,
            reasoning_effort=turn.reasoning_effort,
            include_thoughts=turn.deep_thinking,
        )

    def _generate(self, turn: PreparedTurn) -> tuple[str, TurnUsage]:
        """Single-pass generation. Providers return either text or a (text, usage) tuple."""
        llm_response = turn.provider.generate(**self._generation_kwargs(turn), return_usage=True)

        usage = TurnUsage()
        if isinstance(llm_response, tuple) and len(llm_response) == 2:
            answer_raw, raw_usage = llm_response
            usage.absorb(raw_usage)
        else:
            answer_raw = llm_response if llm_response else ""

        if not isinstance(answer_raw, str):
            answer_raw = json.dumps(answer_raw, indent=2) if answer_raw else ""

        usage.citations = getattr(llm_response, 'citations', []) or []
        return answer_raw, usage

    def _finish(self, message: PaperChatMessage, turn: PreparedTurn, answer_raw: str, usage: TurnUsage) -> dict:
        """Extracts citations, fact-checks, records cost, persists the completed message, returns the result payload."""
        session = message.session
        paper = session.paper
        workspace = session.workspace

        cleaned_answer, parsed_visual_citations = self.citation_extractor.extract(answer_raw)
        verified_visual_cits, guard_summary = self.fact_checker.verify(
            source_text=turn.source_text,
            visual_citations=parsed_visual_citations,
            answer_text=cleaned_answer
        )

        # Fallback estimation if the provider omitted token metrics
        tokens_in = usage.prompt_tokens or max(len(turn.prompt) // 4, 1)
        tokens_out = usage.candidates_tokens
        if not tokens_out and (cleaned_answer or usage.thought_process):
            tokens_out = max(len(cleaned_answer + usage.thought_process) // 4, 1)
        total_tokens = tokens_in + tokens_out

        cost = workspace.record_token_usage(
            tokens_in,
            tokens_out,
            model_name=turn.model_name,
            operation_type="chat",
            user=getattr(session, 'user', None),
            tokens_cached=usage.cached_tokens,
            context_metadata={"session_id": str(session.id), "paper_id": str(session.paper_id) if session.paper_id else None}
        )
        session.record_message_cost(tokens_in, tokens_out, cost)

        message.message = cleaned_answer
        message.thinking_process = usage.thought_process
        message.tokens_in = tokens_in
        message.tokens_out = tokens_out
        message.total_tokens = total_tokens
        message.usd_cost = cost
        message.llm_model = turn.model_name
        message.status = 'completed'
        message.completed_at = timezone.now()
        message.citations = usage.citations
        message.visual_citations = verified_visual_cits
        message.hallucination_guard = guard_summary
        message.save(update_fields=[
            'message', 'thinking_process', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost',
            'llm_model', 'status', 'completed_at', 'citations', 'visual_citations', 'hallucination_guard'
        ])

        # Update session title if first turn
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
            "thinking_process": usage.thought_process,
            "citations": usage.citations,
            "visual_citations": verified_visual_cits,
            "hallucination_guard": guard_summary,
            "deep_thinking": turn.deep_thinking,
            "llm_model": turn.model_name,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_cached": usage.cached_tokens,
            "total_tokens": total_tokens,
            "usd_cost": float(cost),
            "session_total_tokens": session.total_tokens,
            "session_total_usd_cost": float(session.total_usd_cost),
            "workspace_monthly_tokens": workspace.tokens_consumed_this_month,
            "workspace_monthly_usd": float(workspace.usd_spent_this_month),
        }

    def _fail(self, message: PaperChatMessage, error: str, log: bool = True) -> dict:
        if log:
            logger.error(f"Paper chat failed for message '{message.id}': {error}")
        message.status = 'failed'
        message.error_message = error
        message.completed_at = timezone.now()
        message.save(update_fields=['status', 'error_message', 'completed_at'])
        return {
            "status": "failed",
            "message_id": str(message.id),
            "session_id": str(message.session.id),
            "error": error,
        }

    @staticmethod
    def _sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
