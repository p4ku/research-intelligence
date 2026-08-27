import re
import json
import logging

logger = logging.getLogger(__name__)


class VisualCitationExtractor:
    """
    Parses and extracts structured visual citations, bounding boxes, page references,
    and evidence quotes from LLM markdown / JSON output.
    """

    def extract(self, raw_text: str) -> tuple[str, list[dict]]:
        """
        Extracts visual citations from structured JSON code blocks or inline markdown citations.

        Returns:
            cleaned_answer (str): Clean answer text with JSON citation metadata extracted.
            visual_citations (list[dict]): List of structured citation objects.
        """
        visual_citations = []
        cleaned_text = raw_text

        # 1. Match ```json:citations\n[ ... ]\n``` block
        citations_block_match = re.search(r'```(?:json:citations|citations)\s*(\[.*?\])\s*```', cleaned_text, re.DOTALL)
        if citations_block_match:
            try:
                parsed_cits = json.loads(citations_block_match.group(1))
                if isinstance(parsed_cits, list):
                    visual_citations.extend(parsed_cits)
                cleaned_text = cleaned_text.replace(citations_block_match.group(0), "").strip()
            except Exception as e:
                logger.warning(f"Failed to parse json:citations block: {e}")

        # 2. Check for structured ```json ... ``` response block containing "visual_citations"
        json_block_match = re.search(r'```json\s*(\{.*?"visual_citations".*?\})\s*```', cleaned_text, re.DOTALL)
        if json_block_match:
            try:
                data = json.loads(json_block_match.group(1))
                if "answer" in data:
                    cleaned_text = data["answer"]
                else:
                    cleaned_text = cleaned_text.replace(json_block_match.group(0), "").strip()
                if "visual_citations" in data and isinstance(data["visual_citations"], list):
                    visual_citations.extend(data["visual_citations"])
            except Exception as e:
                logger.warning(f"Failed to parse json block for visual citations: {e}")

        # 3. Extract inline citations like: [Page 7, Figure 4b, box_2d: [320, 150, 680, 890], quote: "..."]
        inline_pattern = re.compile(
            r'\[(?:Page\s*(\d+))?(?:,\s*([A-Za-z0-9\s._-]+))?(?:,\s*box_2d:\s*(\[[0-9,\s]+\]))?(?:,\s*quote:\s*"([^"]+)")?\]',
            re.IGNORECASE
        )
        for match in inline_pattern.finditer(cleaned_text):
            page_str, label, box_str, quote = match.groups()
            cit = {}
            if page_str:
                try:
                    cit["page"] = int(page_str)
                except ValueError:
                    pass
            if label:
                cit["label"] = label.strip()
            if box_str:
                try:
                    cit["box_2d"] = json.loads(box_str)
                except Exception:
                    pass
            if quote:
                cit["quote"] = quote.strip()

            if cit and cit not in visual_citations:
                visual_citations.append(cit)

        return cleaned_text.strip(), visual_citations
