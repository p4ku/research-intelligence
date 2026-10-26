import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from research_intelligence.models import Paper, PaperMetric
from slr_review.models import (
    AuditSampleCohort,
    ScreeningReview,
    ExtractionReview,
    AdjudicationDispute,
    SLRWorkspaceConfig,
)

logger = logging.getLogger(__name__)


class ConsensusService:
    """
    Quorum & Dispute Engine for SLR Reviews.
    Evaluates independent blind reviews against quorum thresholds,
    detects split votes, escalates to Senior Arbiter disputes,
    and checks if an entire audit cohort is complete.
    """

    @classmethod
    @transaction.atomic
    def record_screening_review(
        cls,
        sample_cohort: AuditSampleCohort,
        paper: Paper,
        reviewer,
        stage: str,
        decision: str,
        exclusion_reason: Optional[str] = None,
        evidence_quotes: Optional[list] = None,
        reviewer_notes: Optional[str] = None,
        time_spent_seconds: Optional[int] = None
    ) -> ScreeningReview:
        """Submits or updates a reviewer's vote and evaluates consensus."""
        stage = 'abstract' if stage in ('abstract', 'abstract_screening') else 'full_text'
        review, created = ScreeningReview.objects.update_or_create(
            sample_cohort=sample_cohort,
            paper=paper,
            reviewer=reviewer,
            stage=stage,
            defaults={
                'pipeline_run': sample_cohort.pipeline_run,
                'decision': decision,
                'exclusion_reason': exclusion_reason,
                'evidence_quotes': evidence_quotes or [],
                'reviewer_notes': reviewer_notes,
                'time_spent_seconds': time_spent_seconds,
            }
        )

        cls.evaluate_paper_consensus(sample_cohort, paper, stage)
        cls.check_cohort_completion(sample_cohort)

        # Update pipeline_run.status_message with live progress
        try:
            total_papers = sample_cohort.sampled_papers.count()
            reviewed_papers_count = ScreeningReview.objects.filter(
                sample_cohort=sample_cohort,
                stage=stage
            ).values('paper_id').distinct().count()
            run = sample_cohort.pipeline_run
            if run and run.status == 'paused':
                run.status_message = f"Awaiting audit ({reviewed_papers_count}/{total_papers} reviewed)"
                run.save(update_fields=['status_message'])
        except Exception as e:
            logger.debug(f"Could not update status_message: {e}")

        return review

    @classmethod
    def _apply_screening_consensus_to_metric(
        cls,
        sample_cohort: AuditSampleCohort,
        paper: Paper,
        stage: str,
        final_decision: str,
        reviews: Optional[list] = None,
        exclusion_reason: Optional[str] = None
    ):
        """Updates PaperMetric status while preserving the original AI decision for stats."""
        stage = 'abstract' if stage in ('abstract', 'abstract_screening') else 'full_text'
        metric = PaperMetric.objects.filter(
            paper=paper,
            pipeline_run=sample_cohort.pipeline_run
        ).first()
        if not metric:
            return

        m_data = dict(metric.metrics_data or {})
        # Preserve original AI decision
        if 'original_ai_screening_status' not in m_data:
            m_data['original_ai_screening_status'] = metric.screening_status

        if final_decision == 'exclude':
            metric.screening_status = 'rejected'
            if not exclusion_reason and reviews:
                for r in reviews:
                    if getattr(r, 'exclusion_reason', None):
                        exclusion_reason = r.exclusion_reason
                        break
            if exclusion_reason:
                m_data['human_exclusion_reason'] = exclusion_reason
                m_data['exclusion_reason'] = exclusion_reason
        elif final_decision == 'include':
            metric.screening_status = 'full_text_passed' if stage in ('full_text', 'full_text_screening') else 'abstract_passed'

        metric.metrics_data = m_data
        metric.save(update_fields=['screening_status', 'metrics_data'])

    @classmethod
    def evaluate_paper_consensus(
        cls,
        sample_cohort: AuditSampleCohort,
        paper: Paper,
        stage: str
    ) -> Dict[str, Any]:
        """
        Evaluates whether paper has met quorum and whether votes agree.
        If votes split, creates an AdjudicationDispute.
        """
        stage = 'abstract' if stage in ('abstract', 'abstract_screening') else 'full_text'
        config = sample_cohort.config
        quorum_size = config.screening_quorum_size

        reviews = list(
            ScreeningReview.objects.filter(
                sample_cohort=sample_cohort,
                paper=paper,
                stage=stage
            ).select_related('reviewer')
        )

        if len(reviews) < quorum_size:
            return {
                "status": "awaiting_quorum",
                "current_votes": len(reviews),
                "required_quorum": quorum_size
            }

        # Check vote agreement
        decisions = [r.decision for r in reviews]
        unique_decisions = set(decisions)

        # Unanimous agreement without 'uncertain'
        if len(unique_decisions) == 1 and 'uncertain' not in unique_decisions:
            unanimous_decision = decisions[0]
            # Close any open dispute if resolved
            AdjudicationDispute.objects.filter(
                sample_cohort=sample_cohort,
                paper=paper,
                stage=stage,
                status='pending'
            ).update(
                status='resolved',
                final_decision=unanimous_decision,
                resolved_at=timezone.now()
            )
            # Propagate unanimous human decision to downstream PaperMetric
            cls._apply_screening_consensus_to_metric(sample_cohort, paper, stage, unanimous_decision, reviews)
            return {
                "status": "consensus_reached",
                "decision": unanimous_decision,
                "votes_count": len(reviews)
            }

        # Split votes or uncertain flags -> escalate to AdjudicationDispute
        metric = PaperMetric.objects.filter(
            paper=paper,
            pipeline_run=sample_cohort.pipeline_run
        ).first()

        evidence_synthesis = {}
        for idx, r in enumerate(reviews, start=1):
            rev_data = {
                "reviewer_name": f"Reviewer {idx}",
                "decision": r.decision,
                "exclusion_reason": r.exclusion_reason,
                "quotes": r.evidence_quotes,
                "notes": r.reviewer_notes
            }
            evidence_synthesis[f"reviewer_{idx}"] = rev_data
            evidence_synthesis[f"reviewer_{idx}_{r.reviewer.username}"] = rev_data

        if metric:
            reasoning = metric.full_text_screening_reasoning if stage in ('full_text', 'full_text_screening') else metric.abstract_screening_reasoning
            evidence_synthesis["ai_agent"] = {
                "status": metric.screening_status,
                "reasoning": reasoning,
                "confidence": (metric.metrics_data or {}).get("confidence", 0.9)
            }

        # Handle conservative_include policy automatically if configured
        if config.tie_breaker_strategy == 'conservative_include' and 'include' in decisions:
            dispute, created = AdjudicationDispute.objects.get_or_create(
                sample_cohort=sample_cohort,
                paper=paper,
                stage=stage,
                defaults={
                    'status': 'resolved',
                    'final_decision': 'include',
                    'resolution_rationale': 'Auto-resolved via conservative_include policy: at least one reviewer voted Include.',
                    'evidence_synthesis': evidence_synthesis,
                    'resolved_at': timezone.now()
                }
            )
            # Propagate include decision to downstream PaperMetric
            cls._apply_screening_consensus_to_metric(sample_cohort, paper, stage, 'include', reviews)
            return {"status": "auto_resolved_conservative", "decision": "include"}

        # Otherwise create / update pending dispute for Senior Arbiter
        dispute, created = AdjudicationDispute.objects.get_or_create(
            sample_cohort=sample_cohort,
            paper=paper,
            stage=stage,
            defaults={
                'status': 'pending',
                'evidence_synthesis': evidence_synthesis
            }
        )
        if not created and dispute.status == 'pending':
            dispute.evidence_synthesis = evidence_synthesis
            dispute.save(update_fields=['evidence_synthesis'])

        return {"status": "dispute_pending", "dispute_id": str(dispute.id)}

    @classmethod
    @transaction.atomic
    def resolve_dispute(
        cls,
        dispute: AdjudicationDispute,
        arbiter,
        final_decision: str,
        resolution_rationale: str,
        final_exclusion_reason: Optional[str] = None
    ) -> AdjudicationDispute:
        """Issues a binding Senior Arbiter ruling on a disputed paper."""
        dispute.arbiter = arbiter
        dispute.final_decision = final_decision
        dispute.final_exclusion_reason = final_exclusion_reason
        dispute.resolution_rationale = resolution_rationale
        dispute.status = 'resolved'
        dispute.resolved_at = timezone.now()
        dispute.save()

        # Update PaperMetric status according to arbiter's ruling
        cls._apply_screening_consensus_to_metric(
            sample_cohort=dispute.sample_cohort,
            paper=dispute.paper,
            stage=dispute.stage,
            final_decision=final_decision,
            exclusion_reason=final_exclusion_reason
        )

        cls.check_cohort_completion(dispute.sample_cohort)
        return dispute

    @classmethod
    @transaction.atomic
    def check_cohort_completion(cls, sample_cohort: AuditSampleCohort) -> bool:
        """
        Evaluates if all sampled papers in cohort satisfy quorum and have no pending disputes.
        If all are resolved, marks cohort complete and automatically triggers Celery resume.
        Uses select_for_update() to prevent race conditions during concurrent reviewer submissions.
        """
        cohort = AuditSampleCohort.objects.select_for_update().select_related('config').filter(id=sample_cohort.id).first()
        if not cohort:
            return False
        if cohort.is_audit_complete:
            return True

        sample_cohort = cohort
        sampled_papers = list(sample_cohort.sampled_papers.all())
        if not sampled_papers:
            sample_cohort.is_audit_complete = True
            sample_cohort.completed_at = timezone.now()
            sample_cohort.save(update_fields=['is_audit_complete', 'completed_at'])
            return True

        stage = sample_cohort.stage

        # Extraction Gate completion
        if stage == 'parameter_extraction':
            reviewed_papers = set(
                ExtractionReview.objects.filter(sample_cohort=sample_cohort)
                .values_list('paper_id', flat=True)
            )
            is_complete = all(p.id in reviewed_papers for p in sampled_papers)
            if is_complete and not sample_cohort.is_audit_complete:
                cls._finalize_cohort(sample_cohort)
            return is_complete

        # Screening Gate completion (Abstract or Full-Text)
        review_stage = 'abstract' if stage == 'abstract_screening' else 'full_text'
        quorum_size = sample_cohort.config.screening_quorum_size

        # 1. Check each paper has reached quorum (single aggregated query eliminating N+1)
        from django.db.models import Count
        papers_with_quorum = (
            ScreeningReview.objects.filter(
                sample_cohort=sample_cohort,
                stage=review_stage,
                paper_id__in=[p.id for p in sampled_papers]
            )
            .values('paper_id')
            .annotate(vote_count=Count('id'))
            .filter(vote_count__gte=quorum_size)
            .count()
        )
        if papers_with_quorum < len(sampled_papers):
            return False

        # 2. Check that no pending disputes remain
        pending_disputes = AdjudicationDispute.objects.filter(
            sample_cohort=sample_cohort,
            status='pending'
        ).exists()

        if pending_disputes:
            return False

        # All papers satisfied quorum and no disputes pending -> finalize cohort
        if not sample_cohort.is_audit_complete:
            cls._finalize_cohort(sample_cohort)

        return True

    @classmethod
    def _finalize_cohort(cls, sample_cohort: AuditSampleCohort):
        """Marks cohort as complete and notifies orchestrator hooks to resume pipeline."""
        sample_cohort.is_audit_complete = True
        sample_cohort.completed_at = timezone.now()
        sample_cohort.save(update_fields=['is_audit_complete', 'completed_at'])
        logger.info(f"AuditSampleCohort {sample_cohort.id} marked COMPLETE. Triggering pipeline resume...")

        # Recompute PRISMA & Agreement metrics
        try:
            from .metrics_service import MetricsService
            MetricsService.compute_prisma_metrics(sample_cohort.pipeline_run)
        except Exception as e:
            logger.error(f"Error computing PRISMA metrics for run {sample_cohort.pipeline_run_id}: {e}", exc_info=True)

        # Wake up pipeline runner
        try:
            from ..tasks.orchestrator_hooks import resume_slr_pipeline_run
            resume_slr_pipeline_run(sample_cohort.pipeline_run_id)
        except Exception as e:
            logger.error(f"Error resuming pipeline run {sample_cohort.pipeline_run_id}: {e}", exc_info=True)
