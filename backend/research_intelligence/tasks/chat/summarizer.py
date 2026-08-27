import logging
from research_intelligence.models import PaperChatSession

logger = logging.getLogger(__name__)


class HierarchicalSessionSummarizer:
    """
    Manages long conversational history by compressing older turns
    into a concise scientific memorandum, saving token budget while preserving critical context.
    """

    def compress_and_update(self, session: PaperChatSession, history_messages, threshold: int = 4) -> None:
        """
        If the completed messages count exceeds the threshold, summarizes turns 0..N-2 into session.summary.
        """
        count = history_messages.count()
        if count < threshold:
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
            # Bound summary to 10 most informative points
            session.summary = "\n".join(summary_lines[-10:])
            session.save(update_fields=['summary', 'updated_at'])

    def build_history_block(self, session: PaperChatSession, history_messages, recent_turns_count: int = 3) -> str:
        """
        Formats the dialogue history for the prompt:
        - Injects previous scientific summary (if present).
        - Injects the last recent_turns_count verbatim.
        """
        history_dialogue = []
        if session.summary:
            history_dialogue.append(f"### Previous Conversation Scientific Summary:\n{session.summary}\n")

        count = history_messages.count()
        recent_turns = history_messages[max(0, count - recent_turns_count):]
        for prev in recent_turns:
            if prev.question:
                history_dialogue.append(f"User: {prev.question}")
            if prev.message:
                history_dialogue.append(f"Assistant: {prev.message}")

        if history_dialogue:
            return "### Conversation Dialogue:\n" + "\n".join(history_dialogue) + "\n\n"
        return ""
