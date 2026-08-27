import re
import difflib
import logging

logger = logging.getLogger(__name__)


def normalize_text_for_matching(text: str) -> str:
    """Normalizes whitespace, line breaks, and lowercases for robust grounding matching."""
    if not text:
        return ""
    # Collapse whitespace and normalize dashes/quotes
    normalized = re.sub(r'[\r\n\t]+', ' ', text)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'[""''„”]', '"', normalized)
    normalized = re.sub(r'[–—]', '-', normalized)
    return normalized.strip().lower()


def extract_quotes_from_text(text: str) -> list[str]:
    """Extracts explicit quote segments delimited by <quote>...</quote> or quotation marks."""
    if not text:
        return []
    quotes = []
    # 1. Look for XML style <quote>...</quote>
    xml_quotes = re.findall(r'<quote>(.*?)</quote>', text, re.DOTALL | re.IGNORECASE)
    quotes.extend([q.strip() for q in xml_quotes if len(q.strip()) > 8])

    # 2. Look for Markdown blockquotes
    blockquotes = re.findall(r'^\s*>\s*(.*?)$', text, re.MULTILINE)
    quotes.extend([b.strip() for b in blockquotes if len(b.strip()) > 10])

    return quotes


def verify_citations_against_source(
    source_text: str,
    visual_citations: list[dict],
    answer_text: str = ""
) -> tuple[list[dict], dict]:
    """
    Deterministic fact-checker and hallucination guard.
    Verifies that cited quotes and evidence statements exist verbatim or near-verbatim in the source text.
    
    Returns (verified_visual_citations, hallucination_guard_summary).
    """
    norm_source = normalize_text_for_matching(source_text)
    if not norm_source:
        return visual_citations, {
            "verified": False,
            "grounding_score": 0.0,
            "verified_count": 0,
            "total_count": len(visual_citations),
            "status": "UNVERIFIED_EMPTY_SOURCE"
        }

    verified_citations = []
    total_checked = 0
    verified_count = 0

    # 1. Verify structured visual_citations
    for cit in (visual_citations or []):
        cit_copy = dict(cit)
        quote_str = cit_copy.get("quote") or cit_copy.get("text") or cit_copy.get("evidence") or ""
        
        if quote_str and len(quote_str.strip()) > 5:
            total_checked += 1
            norm_quote = normalize_text_for_matching(quote_str)
            
            # Exact substring match
            if norm_quote in norm_source:
                cit_copy["verified_in_source"] = True
                cit_copy["match_confidence"] = 1.0
                verified_count += 1
            else:
                # Fuzzy ratio matching for slight OCR or punctuation discrepancies
                # Split quote into chunks if long
                match_ratio = difflib.SequenceMatcher(None, norm_quote, norm_source).quick_ratio()
                
                # Check for significant substring match
                words = norm_quote.split()
                sub_matched = False
                if len(words) >= 4:
                    sub_phrase = " ".join(words[:min(6, len(words))])
                    if sub_phrase in norm_source:
                        sub_matched = True

                if sub_matched or match_ratio > 0.85:
                    cit_copy["verified_in_source"] = True
                    cit_copy["match_confidence"] = round(max(match_ratio, 0.9), 2)
                    verified_count += 1
                else:
                    cit_copy["verified_in_source"] = False
                    cit_copy["match_confidence"] = round(match_ratio, 2)
        else:
            # Citation has no specific quote to check (e.g. only page reference)
            cit_copy["verified_in_source"] = True
            cit_copy["match_confidence"] = 1.0

        verified_citations.append(cit_copy)

    # 2. Also check inline extracted quotes in the answer
    inline_quotes = extract_quotes_from_text(answer_text)
    for q in inline_quotes:
        total_checked += 1
        norm_q = normalize_text_for_matching(q)
        if norm_q in norm_source:
            verified_count += 1
        else:
            words = norm_q.split()
            if len(words) >= 4 and " ".join(words[:4]) in norm_source:
                verified_count += 1

    # 3. Calculate final grounding score
    if total_checked == 0:
        grounding_score = 1.0
        guard_status = "PASS_NO_EXPLICIT_CITATIONS"
        is_verified = True
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
