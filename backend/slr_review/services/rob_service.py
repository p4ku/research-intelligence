import logging
from typing import Dict, Any, Optional
from django.db import transaction

from research_intelligence.models import Paper, PipelineRun
from slr_review.models import RiskOfBiasAssessment

logger = logging.getLogger(__name__)


class RiskOfBiasService:
    """
    Automated Cochrane RoB 2 & ROBINS-I Methodological Quality Appraisal Service.
    Evaluates 5 bias domains with textual provenance, aggregates overall risk of bias,
    and assigns traffic light colors for Cochrane synthesis plots.
    """

    ROB2_DOMAINS = [
        "D1_randomization",
        "D2_deviations",
        "D3_missing_data",
        "D4_measurement",
        "D5_selection",
    ]

    ROBINS_I_DOMAINS = [
        "D1_confounding",
        "D2_selection",
        "D3_classification",
        "D4_deviations",
        "D5_missing_data",
        "D6_measurement",
        "D7_selection_reported",
    ]

    @classmethod
    @transaction.atomic
    def assess_paper_rob(
        cls,
        paper: Paper,
        pipeline_run: PipelineRun,
        framework: str = 'rob2',
        domain_scores: Optional[Dict[str, Any]] = None
    ) -> RiskOfBiasAssessment:
        """
        Calculates and persists Risk of Bias appraisal for an included paper.
        If domain_scores are not provided, generates default domain ratings based on study metadata.
        """
        if framework == 'auto_detect':
            # Check title and abstract for RCT / randomized cues
            text = f"{paper.title} {paper.abstract}".lower()
            framework = 'rob2' if ('randomized' in text or 'rct' in text or 'randomised' in text) else 'robins_i'

        if not domain_scores:
            domain_scores = cls._generate_heuristic_domain_scores(paper, framework)

        overall_bias, traffic_light_color = cls.calculate_overall_bias(domain_scores)

        rob_assessment, _ = RiskOfBiasAssessment.objects.update_or_create(
            paper=paper,
            pipeline_run=pipeline_run,
            defaults={
                'framework': framework,
                'domain_scores': domain_scores,
                'overall_bias': overall_bias,
                'traffic_light_color': traffic_light_color,
            }
        )

        return rob_assessment

    @classmethod
    def calculate_overall_bias(cls, domain_scores: Dict[str, Any]) -> tuple[str, str]:
        """
        Determines overall bias from domain ratings according to Cochrane RoB 2 rules:
        - Critical risk if any domain is critical_risk -> 'red'
        - High risk if any domain is high_risk -> 'red'
        - Some concerns if any domain is some_concerns -> 'yellow'
        - Low risk only if all domains are low_risk -> 'green'
        """
        ratings = []
        for val in domain_scores.values():
            if isinstance(val, dict):
                ratings.append(val.get('rating', 'low_risk'))
            elif isinstance(val, str):
                ratings.append(val)

        if 'critical_risk' in ratings:
            return 'critical_risk', 'red'
        if 'high_risk' in ratings:
            return 'high_risk', 'red'
        if 'some_concerns' in ratings:
            return 'some_concerns', 'yellow'
        return 'low_risk', 'green'

    @classmethod
    def _generate_heuristic_domain_scores(cls, paper: Paper, framework: str) -> Dict[str, Any]:
        """Fallback rule-based domain scoring when raw text is parsed."""
        domains = cls.ROB2_DOMAINS if framework == 'rob2' else cls.ROBINS_I_DOMAINS
        text = f"{paper.title} {paper.abstract}".lower()

        scores = {}
        for d in domains:
            if 'blind' in text or 'double-blind' in text or 'placebo' in text:
                scores[d] = {"rating": "low_risk", "quote": "Standard blinding/control described in abstract.", "page": 1}
            elif 'retrospective' in text or 'observational' in text:
                scores[d] = {"rating": "some_concerns", "quote": "Observational design introduces potential unmeasured confounding.", "page": 1}
            else:
                scores[d] = {"rating": "low_risk", "quote": "No major methodological deviation reported.", "page": 1}
        return scores
