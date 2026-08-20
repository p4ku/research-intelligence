import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings

from research_intelligence.scrapers.arxiv import ArxivScraperProvider
from research_intelligence.scrapers.openalex import OpenAlexScraperProvider
from research_intelligence.scrapers.lens import LensScraperProvider


class ScraperParsersAndPaginationTestCase(TestCase):
    """
    Unit tests for real payload parsing, inverted index abstract reconstruction,
    author list formatting, and error resilience across academic scrapers (arXiv, OpenAlex, Lens).
    """

    @patch("research_intelligence.scrapers.arxiv.urllib.request.urlopen")
    def test_arxiv_xml_atom_response_parsing(self, mock_urlopen):
        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title> Scalable High-Temperature Superconductors </title>
    <summary> We report a new room temperature superconducting phase. </summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
    <published>2024-01-15T12:00:00Z</published>
  </entry>
</feed>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = atom_xml.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = ArxivScraperProvider()
        results = provider.search("superconductors", limit=5)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["title"], "Scalable High-Temperature Superconductors")
        self.assertEqual(item["hash_id"], "2401.12345")
        self.assertIn("Alice Smith", item["authors"])
        self.assertIn("Bob Jones", item["authors"])
        self.assertEqual(item["pdf_url"], "http://arxiv.org/pdf/2401.12345v1")

    @patch("research_intelligence.scrapers.openalex.urllib.request.urlopen")
    def test_openalex_inverted_index_abstract_reconstruction(self, mock_urlopen):
        openalex_json = {
            "results": [
                {
                    "id": "https://openalex.org/W2741809807",
                    "title": "Quantum Error Mitigation for NISQ Devices",
                    "publication_date": "2023-11-20",
                    "authorships": [
                        {"author": {"display_name": "Charlie Brown"}},
                        {"author": {"display_name": "Diana Prince"}}
                    ],
                    # Inverted index: {word: [positions]}
                    "abstract_inverted_index": {
                        "Quantum": [0],
                        "error": [1],
                        "mitigation": [2],
                        "is": [3],
                        "critical": [4],
                        "for": [5],
                        "NISQ": [6],
                        "computing.": [7]
                    },
                    "best_oa_location": {
                        "pdf_url": "https://arxiv.org/pdf/2311.99999.pdf"
                    },
                    "doi": "https://doi.org/10.1103/PhysRevA.99.012345"
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openalex_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = OpenAlexScraperProvider()
        results = provider.search("quantum error mitigation", limit=5)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["title"], "Quantum Error Mitigation for NISQ Devices")
        self.assertEqual(item["abstract"], "Quantum error mitigation is critical for NISQ computing.")
        self.assertEqual(item["authors"], "Charlie Brown, Diana Prince")
        self.assertEqual(item["pdf_url"], "https://arxiv.org/pdf/2311.99999.pdf")
        self.assertEqual(item["other_url"], "https://doi.org/10.1103/PhysRevA.99.012345")

    def test_lens_scraper_without_api_key_returns_empty_list_safely(self):
        with override_settings(LENS_API_KEY=None):
            provider = LensScraperProvider()
            results = provider.search("solid state battery")
            self.assertEqual(results, [])

    @patch("research_intelligence.scrapers.lens.urllib.request.urlopen")
    def test_lens_scholarly_json_response_parsing(self, mock_urlopen):
        lens_json = {
            "data": [
                {
                    "lens_id": "012-345-678-901-234",
                    "title": "Silicon Anode Degradation in Lithium Batteries",
                    "date_published": "2024-02-01",
                    "abstract": "We analyze capacity fade in silicon anodes.",
                    "authors": [
                        {"display_name": "Eva Green"}
                    ],
                    "source_urls": [
                        {"url": "https://publisher.com/article.pdf"}
                    ],
                    "external_ids": [
                        {"type": "doi", "value": "10.1016/j.jpowsour.2024.01"}
                    ]
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(lens_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with override_settings(LENS_API_KEY="test_mock_lens_key"):
            provider = LensScraperProvider()
            results = provider.search("silicon anode", limit=5)

            self.assertEqual(len(results), 1)
            item = results[0]
            self.assertEqual(item["title"], "Silicon Anode Degradation in Lithium Batteries")
            self.assertEqual(item["authors"], "Eva Green")
            self.assertEqual(item["pdf_url"], "https://publisher.com/article.pdf")
            self.assertEqual(item["other_url"], "https://www.lens.org/lens/scholar/article/012-345-678-901-234")
