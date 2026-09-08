import logging
from chat.models import PaperChatSession

logger = logging.getLogger(__name__)


class HierarchicalSessionSummarizer:
    """
    Manages session compression and context memory for academic paper chat sessions.
    Automatically condenses older turns into an evolving scientific summary while preserving
    the most recent conversational turns verbatim.
    """

    RECENT_TURNS = 3

    def compress_and_update(self, session: PaperChatSession, history_messages, threshold: int = 4) -> None:
        """
        Abridges every turn older than the RECENT_TURNS kept verbatim into session.summary,
        once the history is at least `threshold` long.
        """
        count = len(history_messages)
        if count < threshold:
            return

        older_messages = history_messages[:-self.RECENT_TURNS]
        if not older_messages:
            return
        new_summary_items = []
        for msg in older_messages:
            q_snippet = msg.question[:120] + "..." if len(msg.question) > 120 else msg.question
            a_snippet = msg.message[:150] + "..." if len(msg.message) > 150 else msg.message
            new_summary_items.append(f"Q: {q_snippet}\nA: {a_snippet}")

        incremental_summary = "\n---\n".join(new_summary_items)
        session.summary = incremental_summary.strip()
        session.save(update_fields=['summary', 'updated_at'])
        logger.info(f"Updated hierarchical summary for session '{session.id}' (Turn count: {count})")

    def build_history_block(self, session: PaperChatSession, history_messages, recent_turns_count: int = RECENT_TURNS) -> str:
        """
        Formats the combined historical summary and recent turns into a prompt memory block.
        """
        recent_messages = history_messages[-recent_turns_count:] if len(history_messages) > recent_turns_count else history_messages
        history_parts = []

        if session.summary and session.summary.strip():
            history_parts.append(f"### Earlier Turns (abridged: questions cut at 120 characters, answers at 150)\n{session.summary.strip()}")

        if recent_messages:
            recent_turns = []
            for msg in recent_messages:
                recent_turns.append(f"User: {msg.question}\nAssistant: {msg.message}")
            history_parts.append("### Recent Conversation Turns\n" + "\n\n".join(recent_turns))

        return "\n\n".join(history_parts)
