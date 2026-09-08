import re
import logging

logger = logging.getLogger(__name__)


class CitationFactChecker:
    """
    Deterministic fact-checking and hallucination guard that validates extracted citations
    and quotes against the original source document text (Markdown or OCR/abstract).
    """

    def _normalize_text(self, text: str) -> str:
        """Normalizes whitespace and lowercases string for robust fuzzy matching."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.strip()).lower()

    def _fuzzy_quote_in_text(self, quote: str, source_text: str, threshold: float = 0.75) -> bool:
        """
        Determines if a quoted excerpt exists in the source document using substring matching
        or token-level n-gram overlap.
        """
        if not quote or not source_text:
            return False

        norm_quote = self._normalize_text(quote)
        norm_source = self._normalize_text(source_text)

        # 1. Exact normalized substring match
        if norm_quote in norm_source:
            return True

        # 2. Token overlap heuristic (for slight OCR discrepancies)
        quote_words = [w for w in re.findall(r'\b\w+\b', norm_quote) if len(w) > 2]
        if not quote_words:
            return False

        matched_words = sum(1 for w in quote_words if w in norm_source)
        ratio = matched_words / len(quote_words)
        return ratio >= threshold

    def verify(
        self,
        source_text: str,
        visual_citations: list[dict],
        answer_text: str = ""
    ) -> tuple[list[dict], dict]:
        """
        Audits visual citations and referenced claims against the source document.

        Returns:
            verified_citations (list[dict]): Updated citations with verification flags and ground truth locations.
            guard_summary (dict): Audit summary containing score, verification status, and flag details.
        """
        verified_citations = []
        verified_count = 0
        total_checked = 0

        for cit in visual_citations:
            quote = cit.get("quote", "")
            label = cit.get("label", "")
            is_valid = False

            if quote:
                total_checked += 1
                is_valid = self._fuzzy_quote_in_text(quote, source_text)
                if is_valid:
                    verified_count += 1
            elif label:
                total_checked += 1
                is_valid = self._fuzzy_quote_in_text(label, source_text, threshold=0.85)
                if is_valid:
                    verified_count += 1
            else:
                # Page only without quote
                is_valid = True

            cit_entry = dict(cit)
            cit_entry["verified_in_source"] = is_valid
            verified_citations.append(cit_entry)

        # Check for direct quotation marks inside answer text. Marker quotes are
        # still present in the answer text and were counted above, so skip them.
        marker_quotes = {cit.get("quote", "") for cit in visual_citations if cit.get("quote")}
        inline_quotes = [q for q in re.findall(r'"([^"]{15,})"', answer_text) if q not in marker_quotes]
        for q in inline_quotes:
            total_checked += 1
            if self._fuzzy_quote_in_text(q, source_text):
                verified_count += 1

        if total_checked == 0:
            grounding_score = 1.0
            is_verified = True
            guard_status = "PASS_NO_EXPLICIT_QUOTES"
        else:
            grounding_score = round(verified_count / total_checked, 2)
            is_verified = grounding_score >= 0.8
            guard_status = "PASS" if is_verified else "WARNING_UNVERIFIED_CLAIMS"

        guard_summary = {
            "verified": is_verified,
            "grounding_score": grounding_score,
            "verified_count": verified_count,
            "total_count": total_checked,
            "status": guard_status
        }

        return verified_citations, guard_summary
