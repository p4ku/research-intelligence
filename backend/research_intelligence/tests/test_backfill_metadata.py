from unittest.mock import patch, MagicMock
from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from research_intelligence.models import Workspace, PipelineRun, Paper, DocumentRegistry


class BackfillMetadataCommandTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Metadata Test WS")
        self.run = PipelineRun.objects.create(workspace=self.workspace, status="completed")

        self.doc_arxiv = DocumentRegistry.objects.create(
            sha256_hash="hash_arxiv_001",
            title="Oraqle: An Empirical Analysis",
            arxiv_id="2608.01939",
            meta={}
        )
        self.paper_arxiv = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="paper_arxiv_001",
            title="Oraqle: An Empirical Analysis",
            arxiv_id="2608.01939",
            document_registry=self.doc_arxiv,
            meta={}
        )

        self.doc_oa = DocumentRegistry.objects.create(
            sha256_hash="hash_oa_001",
            title="Quantum Machine Learning",
            doi="10.1038/nature23474",
            primary_source="openalex",
            meta={}
        )
        self.paper_oa = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="paper_oa_001",
            title="Quantum Machine Learning",
            doi="10.1038/nature23474",
            document_registry=self.doc_oa,
            meta={}
        )

    @patch("urllib.request.urlopen")
    def test_backfill_metadata_arxiv_and_openalex(self, mock_urlopen):
        atom_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2608.01939v2</id>
    <title>Oraqle: An Empirical Analysis of Qubit Readout</title>
    <summary>Quantum error correction requires fast readout.</summary>
    <author><name>Emmanouil Giortamis</name></author>
    <published>2026-08-03T09:13:15Z</published>
    <updated>2026-08-11T13:07:26Z</updated>
  </entry>
</feed>"""

        openalex_json = b"""{
            "id": "https://openalex.org/W2741809807",
            "doi": "https://doi.org/10.1038/nature23474",
            "title": "Quantum machine learning"
        }"""

        def mock_side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            resp = MagicMock()
            if "arxiv.org" in url:
                resp.read.return_value = atom_xml
            else:
                resp.read.return_value = openalex_json
            resp.__enter__.return_value = resp
            return resp

        mock_urlopen.side_effect = mock_side_effect

        out = StringIO()
        call_command('backfill_metadata', '--delay', '0.01', '--batch-size', '5', stdout=out)

        self.doc_arxiv.refresh_from_db()
        self.paper_arxiv.refresh_from_db()
        self.assertIn("id", self.doc_arxiv.meta)
        self.assertEqual(self.doc_arxiv.meta["id"], "http://arxiv.org/abs/2608.01939v2")
        self.assertEqual(self.paper_arxiv.meta["id"], "http://arxiv.org/abs/2608.01939v2")

        self.doc_oa.refresh_from_db()
        self.paper_oa.refresh_from_db()
        self.assertEqual(self.doc_oa.meta["id"], "https://openalex.org/W2741809807")
        self.assertEqual(self.paper_oa.meta["id"], "https://openalex.org/W2741809807")

    @patch("urllib.request.urlopen")
    def test_backfill_metadata_dry_run_does_not_mutate(self, mock_urlopen):
        atom_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2608.01939v2</id>
    <title>Oraqle</title>
  </entry>
</feed>"""
        resp = MagicMock()
        resp.read.return_value = atom_xml
        resp.__enter__.return_value = resp
        mock_urlopen.return_value = resp

        out = StringIO()
        call_command('backfill_metadata', '--dry-run', '--delay', '0.01', '--source', 'arxiv', stdout=out)

        self.doc_arxiv.refresh_from_db()
        self.assertEqual(self.doc_arxiv.meta, {})
