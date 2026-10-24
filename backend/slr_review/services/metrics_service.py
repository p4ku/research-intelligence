import logging
from typing import Dict, Any, Tuple, Optional
from collections import Counter
from django.db import transaction

from research_intelligence.models import PipelineRun, PaperMetric
from slr_review.models import SLRPRISMAMetrics, ScreeningReview

logger = logging.getLogger(__name__)


class MetricsService:
    """
    Statistical Reliability & PRISMA 2020 Flow Metrics Engine.
    Aggregates flow stage numbers and computes Cohen's Kappa (κ),
    AI sensitivity, and specificity against human consensus.
    """

    @classmethod
    @transaction.atomic
    def compute_prisma_metrics(cls, pipeline_run: PipelineRun) -> SLRPRISMAMetrics:
        """Computes and updates PRISMA 2020 statement counts for pipeline_run."""
        metrics_qs = PaperMetric.objects.filter(pipeline_run=pipeline_run)

        # Identification & Deduplication
        total_identified = metrics_qs.count()
        # In multi-source ingestion, duplicates_removed may be recorded in pipeline_run.configuration_override
        dups_removed = (pipeline_run.configuration_override or {}).get('duplicates_removed', 0)

        # Full-Text Screening (papers that passed or were evaluated at full-text)
        from django.db.models import Q
        has_ft_eval = Q(full_text_screening_reasoning__isnull=False) & ~Q(full_text_screening_reasoning='')
        full_text_candidates = metrics_qs.filter(
            Q(screening_status__in=['full_text_passed', 'accepted']) |
            (Q(screening_status__in=['rejected', 'borderline']) & has_ft_eval)
        )
        full_text_assessed = full_text_candidates.count()
        full_text_excluded_count = full_text_candidates.filter(screening_status='rejected').count()

        # Abstract Screening (papers rejected before full-text)
        abstract_screened = total_identified
        abstract_excluded_qs = metrics_qs.filter(screening_status='rejected').exclude(has_ft_eval)
        abstract_excluded_count = abstract_excluded_qs.count()

        # Reasons tally
        abstract_reasons = Counter()
        for m in abstract_excluded_qs:
            reason = (m.metrics_data or {}).get('exclusion_reason') or 'Eligibility criteria not met'
            abstract_reasons[reason] += 1

        full_text_reasons = Counter()
        reviews = ScreeningReview.objects.filter(
            pipeline_run=pipeline_run,
            stage='full_text',
            decision='exclude'
        ).exclude(exclusion_reason__isnull=True)
        for r in reviews:
            if r.exclusion_reason:
                full_text_reasons[r.exclusion_reason] += 1

        # Included studies
        included_synthesis = metrics_qs.filter(
            screening_status__in=['full_text_passed', 'accepted']
        ).count()

        # Statistical Agreement Metrics
        human_kappa = cls.calculate_human_inter_rater_kappa(pipeline_run)
        ai_kappa, sensitivity, specificity = cls.calculate_ai_agreement_metrics(pipeline_run)

        prisma_obj, _ = SLRPRISMAMetrics.objects.update_or_create(
            pipeline_run=pipeline_run,
            defaults={
                'records_identified_total': total_identified,
                'duplicates_removed': dups_removed,
                'records_screened_abstract': abstract_screened,
                'records_excluded_abstract': abstract_excluded_count,
                'abstract_exclusion_reasons': dict(abstract_reasons),
                'full_text_assessed': full_text_assessed,
                'full_text_excluded': full_text_excluded_count,
                'full_text_exclusion_reasons': dict(full_text_reasons),
                'studies_included_synthesis': included_synthesis,
                'studies_included_meta_analysis': included_synthesis,
                'human_inter_rater_kappa': human_kappa,
                'ai_vs_human_kappa': ai_kappa,
                'ai_sensitivity': sensitivity,
                'ai_specificity': specificity,
            }
        )

        return prisma_obj

    @classmethod
    def calculate_cohens_kappa(cls, r1_decisions: list, r2_decisions: list) -> Optional[float]:
        """Calculates Cohen's Kappa statistic between two paired raters."""
        if not r1_decisions or len(r1_decisions) != len(r2_decisions):
            return None

        n = len(r1_decisions)
        if n == 0:
            return None

        categories = sorted(list(set(r1_decisions) | set(r2_decisions)))
        if len(categories) <= 1:
            return 1.0  # Perfect agreement on single category

        # Observed agreement
        observed_agreement = sum(1 for a, b in zip(r1_decisions, r2_decisions) if a == b) / n

        # Expected chance agreement
        r1_counts = Counter(r1_decisions)
        r2_counts = Counter(r2_decisions)
        expected_agreement = sum((r1_counts[c] / n) * (r2_counts[c] / n) for c in categories)

        if expected_agreement >= 1.0:
            return 1.0

        kappa = (observed_agreement - expected_agreement) / (1.0 - expected_agreement)
        return round(max(0.0, min(1.0, kappa)), 4)

    @classmethod
    def calculate_human_inter_rater_kappa(cls, pipeline_run: PipelineRun) -> Optional[float]:
        """Calculates Cohen's Kappa between Reviewer 1 and Reviewer 2 on sampled papers."""
        reviews = ScreeningReview.objects.filter(pipeline_run=pipeline_run).select_related('paper', 'reviewer')
        by_paper = {}
        for r in reviews:
            by_paper.setdefault(r.paper_id, []).append(r)

        r1_votes = []
        r2_votes = []
        for p_id, p_reviews in by_paper.items():
            if len(p_reviews) >= 2:
                r1_votes.append(p_reviews[0].decision)
                r2_votes.append(p_reviews[1].decision)

        return cls.calculate_cohens_kappa(r1_votes, r2_votes)

    @classmethod
    def calculate_ai_agreement_metrics(cls, pipeline_run: PipelineRun) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Calculates Cohen's Kappa, Sensitivity, and Specificity between AI predictions
        and Human Consensus ground truth.
        """
        reviews = ScreeningReview.objects.filter(pipeline_run=pipeline_run).select_related('paper')
        by_paper = {}
        for r in reviews:
            by_paper.setdefault(r.paper_id, []).append(r.decision)

        ai_votes = []
        human_votes = []
        tp = fp = tn = fn = 0

        for paper_id, human_decisions in by_paper.items():
            # Consensus vote
            consensus = 'include' if human_decisions.count('include') >= human_decisions.count('exclude') else 'exclude'

            metric = PaperMetric.objects.filter(paper_id=paper_id, pipeline_run=pipeline_run).first()
            if not metric:
                continue
            m_data = metric.metrics_data or {}
            orig_ai_status = m_data.get('original_ai_screening_status', metric.screening_status)
            ai_decision = 'include' if orig_ai_status in ('abstract_passed', 'full_text_passed', 'accepted') else 'exclude'

            ai_votes.append(ai_decision)
            human_votes.append(consensus)

            if ai_decision == 'include' and consensus == 'include':
                tp += 1
            elif ai_decision == 'include' and consensus == 'exclude':
                fp += 1
            elif ai_decision == 'exclude' and consensus == 'exclude':
                tn += 1
            elif ai_decision == 'exclude' and consensus == 'include':
                fn += 1

        kappa = cls.calculate_cohens_kappa(ai_votes, human_votes)
        sensitivity = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0
        specificity = round(tn / (tn + fp), 4) if (tn + fp) > 0 else 1.0

        return kappa, sensitivity, specificity
