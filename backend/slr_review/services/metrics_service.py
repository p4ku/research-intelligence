import logging
from typing import Dict, Any, Tuple, Optional
from collections import Counter
from django.db import transaction

from research_intelligence.models import PipelineRun, PaperMetric, ComponentRun
from slr_review.models import SLRPRISMAMetrics, ScreeningReview, AdjudicationDispute

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
        from django.db.models import Q, Count
        metrics_qs = PaperMetric.objects.filter(pipeline_run=pipeline_run)

        # Identification & Deduplication
        abstract_screened = metrics_qs.count()
        dups_removed = int((pipeline_run.configuration_override or {}).get('duplicates_removed', 0) or 0)
        if dups_removed == 0:
            search_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='search')
            for sr in search_runs:
                sr_metrics = sr.metrics or {}
                dups_removed += int(sr_metrics.get('duplicates_count', 0) or sr_metrics.get('duplicates_removed', 0) or 0)

        total_identified = abstract_screened + dups_removed

        records_by_source = {}
        for row in metrics_qs.values('paper__source_database').annotate(cnt=Count('id')):
            src = row['paper__source_database'] or 'unknown'
            records_by_source[src] = row['cnt']

        # Full-Text Screening (papers that passed or were evaluated at full-text)
        has_ft_eval = Q(full_text_screening_reasoning__isnull=False) & ~Q(full_text_screening_reasoning='')
        full_text_candidates = metrics_qs.filter(
            Q(screening_status__in=['full_text_passed', 'accepted']) |
            (Q(screening_status__in=['rejected', 'borderline']) & has_ft_eval)
        )
        full_text_assessed = full_text_candidates.count()
        ft_excluded_qs = full_text_candidates.filter(screening_status='rejected')
        full_text_excluded_count = ft_excluded_qs.count()

        # Abstract Screening (papers rejected before full-text)
        abstract_excluded_qs = metrics_qs.filter(screening_status='rejected').exclude(has_ft_eval)
        abstract_excluded_count = abstract_excluded_qs.count()

        # Resolved disputes lookup by (paper_id, stage)
        resolved_disputes = {
            (d.paper_id, 'abstract' if d.stage in ('abstract', 'abstract_screening') else 'full_text'): d
            for d in AdjudicationDispute.objects.filter(
                sample_cohort__pipeline_run=pipeline_run,
                status='resolved'
            )
        }

        # Abstract exclusion reasons tally
        abstract_reasons = Counter()
        abs_review_reasons = {}
        for sr in ScreeningReview.objects.filter(
            pipeline_run=pipeline_run,
            stage='abstract',
            decision='exclude'
        ).exclude(exclusion_reason__isnull=True).exclude(exclusion_reason='').order_by('submitted_at', 'id'):
            abs_review_reasons.setdefault(sr.paper_id, sr.exclusion_reason)

        for row in abstract_excluded_qs.values('paper_id', 'metrics_data'):
            pid = row['paper_id']
            m_data = row['metrics_data'] or {}
            disp = resolved_disputes.get((pid, 'abstract'))
            reason = (
                (disp.final_exclusion_reason if disp and disp.final_decision == 'exclude' and disp.final_exclusion_reason else None)
                or m_data.get('human_exclusion_reason')
                or m_data.get('exclusion_reason')
                or abs_review_reasons.get(pid)
                or 'Eligibility criteria not met'
            )
            abstract_reasons[reason] += 1

        # Full-text exclusion reasons tally (1 canonical reason per rejected full-text paper)
        full_text_reasons = Counter()
        ft_review_reasons = {}
        for sr in ScreeningReview.objects.filter(
            pipeline_run=pipeline_run,
            stage='full_text',
            decision='exclude'
        ).exclude(exclusion_reason__isnull=True).exclude(exclusion_reason='').order_by('submitted_at', 'id'):
            ft_review_reasons.setdefault(sr.paper_id, sr.exclusion_reason)

        ft_excluded_rows = list(ft_excluded_qs.values('paper_id', 'metrics_data'))
        if ft_excluded_rows:
            for row in ft_excluded_rows:
                pid = row['paper_id']
                m_data = row['metrics_data'] or {}
                disp = resolved_disputes.get((pid, 'full_text'))
                reason = (
                    (disp.final_exclusion_reason if disp and disp.final_decision == 'exclude' and disp.final_exclusion_reason else None)
                    or m_data.get('human_exclusion_reason')
                    or m_data.get('exclusion_reason')
                    or ft_review_reasons.get(pid)
                    or 'Eligibility criteria not met'
                )
                full_text_reasons[reason] += 1
        else:
            # Fallback if reviews exist without full_text_screening_reasoning populated on PaperMetric
            for pid, r_reason in ft_review_reasons.items():
                disp = resolved_disputes.get((pid, 'full_text'))
                if disp and disp.final_decision == 'include':
                    continue
                full_text_reasons[r_reason] += 1

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
                'records_by_source': records_by_source,
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
        return round(max(-1.0, min(1.0, kappa)), 4)

    @classmethod
    def calculate_human_inter_rater_kappa(cls, pipeline_run: PipelineRun) -> Optional[float]:
        """
        Calculates Cohen's Kappa between Reviewer 1 and Reviewer 2 on sampled papers,
        grouped by (paper_id, stage) with distinct reviewers so cross-stage votes
        from a single reviewer are never paired against each other.
        """
        reviews = (
            ScreeningReview.objects.filter(pipeline_run=pipeline_run)
            .only('paper_id', 'stage', 'reviewer_id', 'decision', 'submitted_at')
            .order_by('submitted_at', 'id')
        )
        by_paper_stage = {}
        for r in reviews:
            norm_stage = 'abstract' if r.stage in ('abstract', 'abstract_screening') else 'full_text'
            key = (r.paper_id, norm_stage)
            stage_map = by_paper_stage.setdefault(key, {})
            stage_map[r.reviewer_id] = r.decision

        r1_votes = []
        r2_votes = []
        for (_p_id, _stage), reviewer_map in by_paper_stage.items():
            if len(reviewer_map) >= 2:
                ordered_decisions = [
                    dec for _rev_id, dec in sorted(reviewer_map.items(), key=lambda kv: str(kv[0]))
                ]
                r1_votes.append(ordered_decisions[0])
                r2_votes.append(ordered_decisions[1])

        return cls.calculate_cohens_kappa(r1_votes, r2_votes)

    @classmethod
    def calculate_ai_agreement_metrics(cls, pipeline_run: PipelineRun) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Calculates Cohen's Kappa, Sensitivity, and Specificity between AI predictions
        and Human Consensus ground truth (honoring Senior Arbiter rulings on split votes).
        """
        reviews = (
            ScreeningReview.objects.filter(pipeline_run=pipeline_run)
            .only('paper_id', 'stage', 'reviewer_id', 'decision', 'submitted_at')
            .order_by('submitted_at', 'id')
        )
        by_paper_stage = {}
        paper_ids = set()
        for r in reviews:
            norm_stage = 'abstract' if r.stage in ('abstract', 'abstract_screening') else 'full_text'
            by_paper_stage.setdefault((r.paper_id, norm_stage), []).append(r.decision)
            paper_ids.add(r.paper_id)

        if not by_paper_stage:
            return None, None, None

        # Batch query PaperMetric and resolved AdjudicationDispute to avoid N+1 queries
        metrics_by_paper = {
            m.paper_id: m
            for m in PaperMetric.objects.filter(
                paper_id__in=paper_ids,
                pipeline_run=pipeline_run
            ).only('paper_id', 'screening_status', 'metrics_data')
        }
        resolved_disputes = {
            (d.paper_id, 'abstract' if d.stage in ('abstract', 'abstract_screening') else 'full_text'): d.final_decision
            for d in AdjudicationDispute.objects.filter(
                sample_cohort__pipeline_run=pipeline_run,
                status='resolved'
            )
            if d.final_decision in ('include', 'exclude')
        }

        ai_votes = []
        human_votes = []
        tp = fp = tn = fn = 0

        for (paper_id, stage), human_decisions in by_paper_stage.items():
            # Consensus vote: honor binding Senior Arbiter ruling if resolved dispute exists
            if (paper_id, stage) in resolved_disputes:
                consensus = resolved_disputes[(paper_id, stage)]
            else:
                consensus = 'include' if human_decisions.count('include') >= human_decisions.count('exclude') else 'exclude'

            metric = metrics_by_paper.get(paper_id)
            if not metric:
                continue
            m_data = metric.metrics_data or {}
            orig_ai_status = (
                m_data.get(f'original_ai_{stage}_status')
                or m_data.get('original_ai_screening_status', metric.screening_status)
            )
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
