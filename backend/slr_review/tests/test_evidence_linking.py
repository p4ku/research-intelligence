import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
    Extraction,
    ExtractionDefinition,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    ExtractionReview,
)

User = get_user_model()


class SLREvidenceLinkingTestCase(TestCase):
    """
    Test suite for Evidence and Extraction Grounding links:
    - Papers with full evidence quotes and page numbers
    - Papers with NO evidence quotes (graceful empty states)
    - Extractions with and without text evidence citations
    - Review submissions capturing verified evidence quotes
    - Contract validation for frontend-backend integration
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='auditor_evidence', password='testpassword123')
        self.client.force_authenticate(user=self.user)

        self.workspace = Workspace.objects.create(name="Evidence Linking Lab")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="member")
        self.config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            screening_quorum_size=1,
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Evidence Test Run",
            status="paused",
            current_stage="awaiting_full_text_screening_audit"
        )

        # Paper 1: Rich with full evidence quotes and page citations
        self.paper_with_evidence = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"hash_ev_{uuid.uuid4().hex}",
            title="Comprehensive Efficacy of Monoclonal Antibodies in Ebola",
            authors="Preston et al.",
            abstract="In this clinical trial, REGN-EB3 demonstrated superior efficacy with mortality reduced to 29% compared to 51% in control arm. Viral load clearance occurred within 48 hours.",
            doi="10.1056/NEJMoa1910993",
            meta={
                "publication_year": 2024,
                "journal": "New England Journal of Medicine"
            },
            original_pdf_path="papers/ebola_trial.pdf"
        )

        self.metric_with_evidence = PaperMetric.objects.create(
            paper=self.paper_with_evidence,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            full_text_screening_reasoning="Definitive RCT evaluating primary endpoints in human cohort.",
            metrics_data={
                "confidence": 0.98,
                "matched_criteria": ["Human Clinical Trial", "Ebola Pathogen", "Survival Outcome"],
                "evidence_quotes": [
                    {
                        "quote": "REGN-EB3 demonstrated superior efficacy with mortality reduced to 29%",
                        "page_number": 3,
                        "section": "Results"
                    },
                    {
                        "quote": "Viral load clearance occurred within 48 hours in early treatment group",
                        "page_number": 5,
                        "section": "Discussion"
                    }
                ]
            }
        )

        # Paper 2: NO evidence quotes (Empty evidence case)
        self.paper_without_evidence = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"hash_no_ev_{uuid.uuid4().hex}",
            title="General Surveillance Notes on Viral Fevers",
            authors="Unknown Consortium",
            abstract="Brief epidemiological bulletin without cited parameters.",
            doi=None,
            meta={"publication_year": 2023},
            original_pdf_path=None  # No PDF binary
        )

        self.metric_without_evidence = PaperMetric.objects.create(
            paper=self.paper_without_evidence,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="rejected",
            full_text_screening_reasoning="Lacks verifiable quantitative clinical data.",
            metrics_data={
                "confidence": 0.82,
                "matched_criteria": []
                # Notice: NO evidence_quotes key here!
            }
        )

        # Screening Cohort containing both papers
        self.screening_cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage="full_text_screening",
            total_pool_count=2,
            sampled_count=2
        )
        self.screening_cohort.sampled_papers.add(self.paper_with_evidence, self.paper_without_evidence)

    def test_paper_with_full_evidence_quotes(self):
        """Tests that PaperDetail endpoint correctly serializes grounding evidence quotes, pages, and sections."""
        url = f"/api/slr/cohorts/{self.screening_cohort.id}/papers/{self.paper_with_evidence.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Evidence verification
        self.assertIn('evidence_quotes', data)
        self.assertEqual(len(data['evidence_quotes']), 2)

        q1 = data['evidence_quotes'][0]
        self.assertEqual(q1['quote'], "REGN-EB3 demonstrated superior efficacy with mortality reduced to 29%")
        self.assertEqual(q1['page_number'], 3)
        self.assertEqual(q1['section'], "Results")

        q2 = data['evidence_quotes'][1]
        self.assertEqual(q2['quote'], "Viral load clearance occurred within 48 hours in early treatment group")
        self.assertEqual(q2['page_number'], 5)
        self.assertEqual(q2['section'], "Discussion")

        # PDF url should be present
        self.assertIsNotNone(data['pdf_url'])
        self.assertIn(str(self.paper_with_evidence.id), data['pdf_url'])

    def test_paper_without_evidence_quotes_graceful_empty_state(self):
        """Tests that a paper with no evidence quotes returns evidence_quotes: [] and 200 OK without errors."""
        url = f"/api/slr/cohorts/{self.screening_cohort.id}/papers/{self.paper_without_evidence.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Must return empty list, not None or missing key
        self.assertIn('evidence_quotes', data)
        self.assertEqual(data['evidence_quotes'], [])
        self.assertEqual(data['matched_criteria'], [])
        self.assertIsNone(data['pdf_url'])
        self.assertEqual(data['ai_decision'], 'exclude')

    def test_extraction_cohort_with_and_without_grounding_evidence(self):
        """Tests parameter extraction stage where some parameters have text evidence & page numbers, and some do not."""
        extraction_cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage="parameter_extraction",
            total_pool_count=1,
            sampled_count=1
        )
        extraction_cohort.sampled_papers.add(self.paper_with_evidence)

        # Definition
        def_r0 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Basic Reproduction Number (R0)",
            system_prompt="Extract R0",
            user_prompt_template="{paper_text}",
            response_schema={}
        )
        def_cfr = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Case Fatality Rate (CFR)",
            system_prompt="Extract CFR",
            user_prompt_template="{paper_text}",
            response_schema={}
        )

        # Extraction 1: Has full text evidence and page number
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper_with_evidence,
            extraction_definition=def_r0,
            category="Epidemiology",
            fields_data={
                "value": "2.45",
                "uncertainty": "95% CI (1.95 - 2.89)",
                "method": "Bayesian MCMC",
                "evidence": "Estimated basic reproduction number R0 of 2.45 (95% CI 1.95–2.89)",
                "page": 4
            }
        )

        # Extraction 2: Has NO text evidence and NO page number
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper_with_evidence,
            extraction_definition=def_cfr,
            category="Clinical",
            fields_data={
                "value": "29%",
                "uncertainty": None,
                "method": "Kaplan-Meier",
                "evidence": None,
                "page": None
            }
        )

        url = f"/api/slr/cohorts/{extraction_cohort.id}/papers/{self.paper_with_evidence.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        extractions = data['extractions']
        self.assertEqual(len(extractions), 2)

        # Parameter 1 with evidence
        ext1 = next(e for e in extractions if e['parameter_name'] == "Basic Reproduction Number (R0)")
        self.assertEqual(ext1['extracted_value'], "2.45")
        self.assertEqual(ext1['uncertainty'], "95% CI (1.95 - 2.89)")
        self.assertEqual(ext1['method'], "Bayesian MCMC")
        self.assertEqual(ext1['text_evidence'], "Estimated basic reproduction number R0 of 2.45 (95% CI 1.95–2.89)")
        self.assertEqual(ext1['page_number'], 4)

        # Parameter 2 without evidence
        ext2 = next(e for e in extractions if e['parameter_name'] == "Case Fatality Rate (CFR)")
        self.assertEqual(ext2['extracted_value'], "29%")
        self.assertIsNone(ext2['uncertainty'])
        self.assertIsNone(ext2['text_evidence'])
        self.assertIsNone(ext2['page_number'])

    def test_submit_extraction_audit_persists_verified_evidence(self):
        """Tests submitting an extraction review action with verified_evidence_quotes and notes."""
        extraction_cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage="parameter_extraction",
            total_pool_count=1,
            sampled_count=1
        )
        extraction_cohort.sampled_papers.add(self.paper_with_evidence)

        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper_with_evidence,
            category="Epidemiology",
            fields_data={"value": "1.8", "evidence": "R0 reported as 1.8", "page": 2}
        )

        audit_url = f"/api/slr/cohorts/{extraction_cohort.id}/extractions/{ext.id}/audit/"
        payload = {
            "action": "verify",
            "verified_evidence_quotes": [
                {"quote": "R0 reported as 1.8", "page": 2}
            ],
            "reviewer_notes": "Grounding verified on page 2 paragraph 1.",
            "time_spent_seconds": 20
        }
        res = self.client.post(audit_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        review = ExtractionReview.objects.get(sample_cohort=extraction_cohort, extraction=ext, reviewer=self.user)
        self.assertEqual(review.action, "verify")
        self.assertEqual(len(review.verified_evidence_quotes), 1)
        self.assertEqual(review.verified_evidence_quotes[0]['page'], 2)
        self.assertEqual(review.reviewer_notes, "Grounding verified on page 2 paragraph 1.")

    def test_schema_contract_conformance_with_frontend(self):
        """Verifies that all required fields expected by frontend auditPaperDetail exist in the API response."""
        expected_fields = {
            'paper_id', 'cohort_id', 'title', 'authors', 'journal', 'publication_year',
            'doi', 'pdf_url', 'has_full_text', 'abstract', 'ai_decision', 'ai_confidence',
            'ai_reasoning', 'matched_criteria', 'evidence_quotes', 'is_reviewed',
            'reviewer_decision', 'exclusion_reason', 'reviewer_note', 'evidence_citation',
            'reviewed_at', 'current_index', 'total_count', 'prev_paper_id', 'next_paper_id',
            'extractions'
        }

        # Check for paper with evidence
        url1 = f"/api/slr/cohorts/{self.screening_cohort.id}/papers/{self.paper_with_evidence.id}/"
        res1 = self.client.get(url1)
        data1 = res1.json()
        missing_fields1 = expected_fields - set(data1.keys())
        self.assertEqual(missing_fields1, set(), f"Missing fields in response: {missing_fields1}")

        # Check for paper without evidence
        url2 = f"/api/slr/cohorts/{self.screening_cohort.id}/papers/{self.paper_without_evidence.id}/"
        res2 = self.client.get(url2)
        data2 = res2.json()
        missing_fields2 = expected_fields - set(data2.keys())
        self.assertEqual(missing_fields2, set(), f"Missing fields in response: {missing_fields2}")
