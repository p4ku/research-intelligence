import re
import json
import logging

logger = logging.getLogger(__name__)


class VisualCitationExtractor:
    """
    Extracts structured visual grounding citations from raw LLM completions.
    Supports structured JSON blocks, markdown page/figure references, and XML <quote> tags.
    """

    def extract(self, raw_text: str) -> tuple[str, list[dict]]:
        """
        Parses visual references and quotes from the LLM text.
        Returns (cleaned_text, visual_citations_list).
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
            except Exception as e:
                logger.debug(f"Failed to parse json:citations block: {e}")

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
