import random
import logging
from typing import List, Optional
from django.db import transaction

from research_intelligence.models import PipelineRun, Paper, PaperMetric, Extraction
from slr_review.models import SLRWorkspaceConfig, AuditSampleCohort

logger = logging.getLogger(__name__)


class SamplingService:
    """
    SLR Sampling Engine.
    Samples papers or parameter extractions at pipeline checkpoint gates
    using pure random or uncertainty-stratified strategies.
    """

    @classmethod
    def get_or_create_config(cls, workspace) -> SLRWorkspaceConfig:
        config = getattr(workspace, 'slr_config', None)
        if not config:
            config, _ = SLRWorkspaceConfig.objects.get_or_create(workspace=workspace)
        return config

    @classmethod
    @transaction.atomic
    def generate_sample_cohort(
        cls,
        pipeline_run: PipelineRun,
        stage: str,
        seed: Optional[int] = None
    ) -> AuditSampleCohort:
        """
        Samples candidates from pipeline_run for human audit at the given checkpoint stage.
        Supported stages: 'abstract_screening', 'full_text_screening', 'parameter_extraction'.
        """
        if seed is not None:
            random.seed(seed)

        workspace = pipeline_run.workspace
        config = cls.get_or_create_config(workspace)

        # 1. Gather candidate pool
        if stage == 'abstract_screening':
            sample_pct = config.abstract_sample_percentage
            metrics = list(
                PaperMetric.objects.filter(pipeline_run=pipeline_run)
                .select_related('paper')
            )
            sampled_papers = cls._sample_papers(metrics, sample_pct, config)
            total_pool_count = len(metrics)

        elif stage == 'full_text_screening':
            sample_pct = config.full_text_sample_percentage
            from django.db.models import Q
            # Only target candidates that actually underwent full-text screening
            # (passed full-text or were rejected with full-text reasoning / retrieval)
            metrics = list(
                PaperMetric.objects.filter(
                    pipeline_run=pipeline_run
                ).filter(
                    Q(screening_status__in=['full_text_passed', 'accepted']) |
                    (Q(screening_status__in=['rejected', 'borderline']) & Q(full_text_screening_reasoning__isnull=False) & ~Q(full_text_screening_reasoning=''))
                ).select_related('paper')
            )
            sampled_papers = cls._sample_papers(metrics, sample_pct, config)
            total_pool_count = len(metrics)

        elif stage == 'parameter_extraction':
            sample_pct = config.extraction_sample_percentage
            extractions = list(
                Extraction.objects.filter(workspace=workspace, paper__metrics__pipeline_run=pipeline_run)
                .select_related('paper')
                .distinct()
            )
            total_pool_count = len(extractions)
            # Sample papers that have extractions
            extraction_papers = list({e.paper for e in extractions})
            target_count = 0 if sample_pct <= 0.0 else (max(1, int(len(extraction_papers) * (sample_pct / 100.0))) if extraction_papers else 0)
            if config.sampling_mode == 'full_audit':
                sampled_papers = extraction_papers
            else:
                sampled_papers = random.sample(extraction_papers, min(target_count, len(extraction_papers)))
        else:
            raise ValueError(f"Unknown SLR audit stage: {stage}")

        strategy_meta = {
            "mode": config.sampling_mode,
            "target_percentage": sample_pct,
            "negative_control_percentage": config.negative_control_percentage if stage != 'parameter_extraction' else 0,
            "seed": seed,
        }

        cohort = AuditSampleCohort.objects.create(
            config=config,
            pipeline_run=pipeline_run,
            stage=stage,
            total_pool_count=total_pool_count,
            sampled_count=len(sampled_papers),
            sampling_strategy=strategy_meta,
            is_audit_complete=(len(sampled_papers) == 0)
        )

        if sampled_papers:
            cohort.sampled_papers.set(sampled_papers)

        logger.info(
            f"Generated AuditSampleCohort {cohort.id} for run {pipeline_run.id} ({stage}): "
            f"{len(sampled_papers)}/{total_pool_count} papers sampled."
        )
        return cohort

    @classmethod
    def _sample_papers(
        cls,
        metrics: List[PaperMetric],
        target_percentage: float,
        config: SLRWorkspaceConfig
    ) -> List[Paper]:
        """Performs selection of papers based on workspace sampling policy."""
        if not metrics:
            return []

        if config.sampling_mode == 'full_audit' or target_percentage >= 100.0:
            return [m.paper for m in metrics]

        total_count = len(metrics)
        target_count = 0 if target_percentage <= 0.0 else max(1, int(round(total_count * (target_percentage / 100.0))))

        if config.sampling_mode == 'pure_random':
            if target_count == 0:
                return []
            selected_metrics = random.sample(metrics, min(target_count, total_count))
            return [m.paper for m in selected_metrics]

        # Uncertainty-stratified sampling (Recommended)
        borderlines = [m for m in metrics if m.screening_status == 'borderline']
        rejected = [m for m in metrics if m.screening_status == 'rejected']
        passed = [m for m in metrics if m.screening_status not in ('borderline', 'rejected')]

        selected_set = set()

        # 1. 100% of borderline / uncertain cases
        for m in borderlines:
            selected_set.add(m.paper)

        # 2. Negative controls (AI-rejected papers to verify no False Negatives)
        neg_val = getattr(config, 'negative_control_percentage', 5.0)
        neg_control_pct = 5.0 if neg_val is None else float(neg_val)
        if neg_control_pct > 0.0 and rejected:
            neg_target = max(1, int(round(len(rejected) * (neg_control_pct / 100.0))))
            for m in random.sample(rejected, min(neg_target, len(rejected))):
                selected_set.add(m.paper)

        # 3. Fill remaining quota from passed papers
        remaining_needed = target_count - len(selected_set)
        if remaining_needed > 0 and passed:
            for m in random.sample(passed, min(remaining_needed, len(passed))):
                selected_set.add(m.paper)

        # If target_count > 0 but nothing drawn yet (due to rounding down), ensure at least 1 paper
        if not selected_set and metrics and target_count > 0:
            selected_set.add(random.choice(metrics).paper)

        return list(selected_set)
