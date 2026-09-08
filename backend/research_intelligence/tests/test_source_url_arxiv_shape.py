"""
The one rule for `arxiv_id` in a link: it must be shaped like an arXiv id.

The arXiv scraper falls back to OpenAlex when arXiv rate-limits, and that
fallback's work id (`W2781738013`) reaches `Paper.arxiv_id` through
`step_1_search/search.py`, which copies `hash_id` for a row labelled `arxiv`.
Minting `https://arxiv.org/abs/W…` from it is a 404 — and migration 0069
backfilled exactly that into `source_url` for rows with no DOI.
"""
from django.test import SimpleTestCase

from research_intelligence.utils.source_url import (
    is_arxiv_id,
    resolve_paper_source_url,
)

OPENALEX_WORK = "https://openalex.org/W2781738013"


class ArxivIdShapeTests(SimpleTestCase):
    def test_accepts_real_arxiv_ids(self):
        for value in ("2401.12345", "0704.0001", "2401.12345v2",
                      "cond-mat/0102536", "cs.CV/0101001", "arXiv:2401.12345"):
            self.assertTrue(is_arxiv_id(value), value)

    def test_rejects_everything_else(self):
        for value in ("W2781738013", "", None, "10.1000/xyz", "abc", "2401.123"):
            self.assertFalse(is_arxiv_id(value), value)


class SourceUrlResolutionTests(SimpleTestCase):
    def test_openalex_work_id_does_not_become_an_arxiv_link(self):
        """The whole bug: a W-id with no DOI used to mint a 404."""
        self.assertEqual(
            resolve_paper_source_url(
                arxiv_id="W2781738013", source_database="arxiv",
                hash_id="W2781738013", meta={"id": OPENALEX_WORK},
            ),
            OPENALEX_WORK,
        )

    def test_backfilled_arxiv_url_with_a_bad_id_is_ignored(self):
        """0069 wrote these; ignoring them re-resolves the row without a migration."""
        self.assertEqual(
            resolve_paper_source_url(
                source_url="https://arxiv.org/abs/W2781738013",
                arxiv_id="W2781738013", meta={"id": OPENALEX_WORK},
            ),
            OPENALEX_WORK,
        )

    def test_a_stored_url_is_otherwise_taken_as_given(self):
        for stored in ("https://arxiv.org/abs/2401.12345", "https://doi.org/10.1/x"):
            self.assertEqual(resolve_paper_source_url(source_url=stored), stored)

    def test_doi_still_wins_over_a_bad_arxiv_id(self):
        self.assertEqual(
            resolve_paper_source_url(arxiv_id="W2781738013", doi="10.1000/xyz"),
            "https://doi.org/10.1000/xyz",
        )

    def test_real_arxiv_ids_still_link_to_arxiv(self):
        for value, expected in (
            ("2401.12345", "https://arxiv.org/abs/2401.12345"),
            ("2401.12345v2", "https://arxiv.org/abs/2401.12345v2"),
            ("cond-mat/0102536", "https://arxiv.org/abs/cond-mat/0102536"),
            ("arXiv:2401.12345", "https://arxiv.org/abs/2401.12345"),
        ):
            self.assertEqual(resolve_paper_source_url(arxiv_id=value), expected)

    def test_nothing_resolvable_is_still_none(self):
        self.assertIsNone(resolve_paper_source_url(arxiv_id="W123", source_database="lens"))
