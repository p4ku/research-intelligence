import logging
from research_intelligence.models import Workspace, Paper
from chat.models import PaperChatSession
from chat.engine import get_llm_provider

logger = logging.getLogger(__name__)


class GeminiContextCacheManager:
    """
    Manages server-side Gemini CachedContent creation, retrieval, and reuse
    for academic paper documents during interactive multi-turn chats.
    """

    def get_or_create_cache(
        self,
        session: PaperChatSession,
        paper: Paper | None,
        workspace: Workspace,
        context_text: str,
        pdf_bytes: bytes | None,
        mime_type: str | None,
        system_instruction: str,
        ttl: str = "3600s",
        provider = None
    ) -> str | None:
        """
        Returns an active CachedContent name if available or creates a new server-side cache.
        Returns None if caching is unsupported, unavailable, or disabled.
        """
        provider_name = getattr(workspace, 'llm_provider', 'google') or 'google'
        if provider_name != 'google':
            return None

        # 1. Reuse existing cache on session if already recorded
        if session.cached_content_name:
            return session.cached_content_name

        # 2. Minimum token threshold to benefit from caching (~1000 tokens / 4KB)
        total_len = len(context_text or "") + (len(pdf_bytes) if pdf_bytes else 0)
        if total_len < 4096:
            return None

        model_name = getattr(workspace, 'screening_llm_model', 'google/gemini-3.8-flash') or 'google/gemini-3.8-flash'
        provider = provider or get_llm_provider(provider_name)

        if not hasattr(provider, 'create_context_cache'):
            return None

        try:
            display_title = paper.title if paper else f"Workspace {workspace.name}"
            contents = []
            if context_text:
                contents.append(f"## ACADEMIC PAPER CONTEXT\n{context_text}")
            if pdf_bytes and mime_type:
                try:
                    from google.genai import types
                    contents.append(types.Part.from_bytes(data=pdf_bytes, mime_type=mime_type))
                except Exception as part_err:
                    logger.debug(f"Could not wrap PDF bytes into GenAI Part: {part_err}")

            cache_name = provider.create_context_cache(
                model=model_name,
                contents=contents,
                ttl=ttl,
                display_name=f"chat_session_{session.id}_{display_title[:30]}",
                system_instruction=system_instruction
            )

            if cache_name:
                session.cached_content_name = cache_name
                session.save(update_fields=['cached_content_name', 'updated_at'])
                logger.info(f"💎 Created Gemini Context Cache '{cache_name}' for chat session '{session.id}'")
                return cache_name

        except Exception as e:
            logger.warning(f"Failed to create Gemini context cache for session {session.id}: {e}")

        return None
