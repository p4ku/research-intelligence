import uuid
import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from research_intelligence.models import Workspace, Paper, PaperMetric, PipelineRun, Extraction
from slr_review.models import (
    SLRWorkspaceConfig,
    SLRProtocol,
    AuditSampleCohort,
    ScreeningReview,
    ExtractionReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
    SLRPRISMAMetrics,
)
from slr_review.services import (
    ConsensusService,
    MetricsService,
    RiskOfBiasService,
)
from slr_review.tasks.orchestrator_hooks import resume_slr_pipeline_run
from .serializers import (
    AuditQueueItemSerializer,
    AuditPaperDetailSerializer,
    SubmitScreeningReviewSerializer,
    SubmitExtractionReviewSerializer,
    AdjudicationDisputeSerializer,
    ResolveDisputeSerializer,
    RiskOfBiasAssessmentSerializer,
    SLRPRISMAMetricsSerializer,
    SLRWorkspaceConfigSerializer,
)

logger = logging.getLogger(__name__)


def check_slr_workspace_access(user, workspace, require_admin: bool = False):
    """
    Verifies that the user has authorized access to the workspace.
    Returns None if authorized, or a 403 Response if access is denied.
    """
    if not user or not user.is_authenticated:
        return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    if user.is_superuser:
        return None

    from research_intelligence.models import WorkspaceMember
    membership = WorkspaceMember.objects.filter(workspace=workspace, user=user).first()
    if not membership:
        from django.conf import settings
        if getattr(settings, 'DEBUG', False):
            has_any_members = WorkspaceMember.objects.filter(workspace=workspace).exists()
            if not has_any_members:
                return None  # Workspace is unassigned/open in debug mode only
        return Response({"error": "Access denied: you are not a member of this workspace."}, status=status.HTTP_403_FORBIDDEN)

    if require_admin and membership.role not in ('admin', 'owner'):
        return Response({"error": "Admin privileges required for this action."}, status=status.HTTP_403_FORBIDDEN)

    return None


class AuditQueueListView(APIView):
    """
    Returns active audit cohorts for the authenticated reviewer.
    Populates the Audit Queue landing table and sidebar badge counter.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Retrieve cohorts from workspaces where user is active or assigned
        cohorts = (
            AuditSampleCohort.objects.all()
            .select_related('pipeline_run', 'config__workspace')
            .order_by('-created_at')
        )
        if not user.is_superuser:
            from research_intelligence.models import WorkspaceMember
            from django.db.models import Q
            user_ws_ids = set(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
            workspaces_with_members = set(WorkspaceMember.objects.values_list('workspace_id', flat=True))
            cohorts = cohorts.filter(
                Q(config__workspace_id__in=user_ws_ids) |
                ~Q(config__workspace_id__in=workspaces_with_members) |
                Q(pipeline_run__triggered_by=user)
            ).distinct()

        results = []
        for cohort in cohorts:
            sampled_ids = list(cohort.sampled_papers.values_list('id', flat=True))
            total_assigned = len(sampled_ids)
            if total_assigned == 0:
                continue

            if cohort.stage == 'parameter_extraction':
                completed_count = ExtractionReview.objects.filter(
                    sample_cohort=cohort,
                    reviewer=user,
                    paper_id__in=sampled_ids
                ).values('paper_id').distinct().count()
            else:
                stage_review = 'abstract' if cohort.stage == 'abstract_screening' else 'full_text'
                completed_count = ScreeningReview.objects.filter(
                    sample_cohort=cohort,
                    reviewer=user,
                    stage=stage_review,
                    paper_id__in=sampled_ids
                ).count()

            remaining_count = max(0, total_assigned - completed_count)

            if cohort.is_audit_complete or remaining_count == 0:
                cohort_status = 'completed'
            elif completed_count > 0:
                cohort_status = 'in_review'
            else:
                cohort_status = 'pending'

            ws = cohort.config.workspace
            run = cohort.pipeline_run

            results.append({
                "cohort_id": cohort.id,
                "pipeline_run_id": run.id,
                "workspace_id": ws.id,
                "workspace_name": ws.name,
                "briefing_name": run.name or ws.name,
                "gate": cohort.stage,
                "assigned_count": total_assigned,
                "completed_count": completed_count,
                "remaining_count": remaining_count,
                "status": cohort_status,
                "created_at": cohort.created_at,
            })

        serializer = AuditQueueItemSerializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AuditCohortDetailView(APIView):
    """Returns cohort details and ordered paper references."""
    permission_classes = [IsAuthenticated]

    def get(self, request, cohort_id):
        cohort = get_object_or_404(
            AuditSampleCohort.objects.select_related('pipeline_run', 'config__workspace'),
            pk=cohort_id
        )
        denied = check_slr_workspace_access(request.user, cohort.config.workspace)
        if denied:
            return denied
        user = request.user

        papers = list(cohort.sampled_papers.all().order_by('created_at', 'id'))
        if cohort.stage == 'parameter_extraction':
            reviewed_paper_ids = set(
                ExtractionReview.objects.filter(
                    sample_cohort=cohort,
                    reviewer=user
                ).values_list('paper_id', flat=True)
            )
        else:
            stage_review = 'abstract' if cohort.stage == 'abstract_screening' else 'full_text'
            reviewed_paper_ids = set(
                ScreeningReview.objects.filter(
                    sample_cohort=cohort,
                    reviewer=user,
                    stage=stage_review
                ).values_list('paper_id', flat=True)
            )

        paper_items = []
        for idx, p in enumerate(papers, start=1):
            paper_items.append({
                "paper_id": p.id,
                "index": idx,
                "title": p.title,
                "doi": p.doi,
                "is_reviewed": p.id in reviewed_paper_ids
            })

        first_unreviewed = next((p["paper_id"] for p in paper_items if not p["is_reviewed"]), None)

        return Response({
            "cohort_id": cohort.id,
            "pipeline_run_id": cohort.pipeline_run_id,
            "stage": cohort.stage,
            "is_audit_complete": cohort.is_audit_complete,
            "total_papers": len(papers),
            "completed_count": len(reviewed_paper_ids),
            "first_unreviewed_paper_id": first_unreviewed or (papers[0].id if papers else None),
            "papers": paper_items
        }, status=status.HTTP_200_OK)


class AuditPaperDetailView(APIView):
    """
    Returns single paper audit payload for the dual-pane Review Workspace.
    Includes PDF streaming link, AI rationale, criteria tags, and user's review status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, cohort_id, paper_id):
        cohort = get_object_or_404(AuditSampleCohort.objects.select_related('pipeline_run', 'config__workspace'), pk=cohort_id)
        denied = check_slr_workspace_access(request.user, cohort.config.workspace)
        if denied:
            return denied
        paper = get_object_or_404(Paper, pk=paper_id)
        if not cohort.sampled_papers.filter(pk=paper.pk).exists():
            return Response({"error": "Paper is not part of this audit cohort."}, status=status.HTTP_404_NOT_FOUND)

        # Get pipeline metric for AI context
        metric = PaperMetric.objects.filter(paper=paper, pipeline_run=cohort.pipeline_run).first()
        stage_review = 'abstract' if cohort.stage == 'abstract_screening' else 'full_text'

        ai_is_included = False
        ai_reasoning = "Evaluated against study eligibility criteria."
        if metric:
            ai_is_included = metric.screening_status in ('abstract_passed', 'full_text_passed', 'accepted')
            ai_reasoning = (
                metric.full_text_screening_reasoning
                if stage_review == 'full_text' and metric.full_text_screening_reasoning
                else (metric.abstract_screening_reasoning or ai_reasoning)
            )

        metrics_data = (metric.metrics_data or {}) if metric else {}
        evidence_quotes = metrics_data.get('evidence_quotes', [])
        matched_criteria = metrics_data.get('matched_criteria', [])
        ai_confidence = float(metrics_data.get('confidence', 0.92))

        # Check existing review by current user
        extractions_list = []
        is_reviewed = False
        reviewer_decision = None
        exclusion_reason = None
        reviewer_note = None
        reviewed_at = None
        evidence_citation = None

        if cohort.stage == 'parameter_extraction':
            paper_extractions = Extraction.objects.filter(
                paper=paper,
                workspace=cohort.config.workspace
            ).select_related('extraction_definition')
            existing_extraction_reviews = {
                er.extraction_id: er
                for er in ExtractionReview.objects.filter(sample_cohort=cohort, reviewer=request.user)
            }
            for ext in paper_extractions:
                fd = ext.fields_data or {}
                val = str(fd.get('value') or fd.get('extracted_value') or ext.exit_metric or 'Reported')
                unc = fd.get('uncertainty') or fd.get('confidence_interval') or fd.get('ci')
                meth = fd.get('method') or fd.get('estimation_method') or ext.confidence_method
                ev = fd.get('evidence') or fd.get('quote') or fd.get('text_evidence')
                if isinstance(ev, list) and ev:
                    ev = ev[0]
                    if isinstance(ev, dict):
                        ev = ev.get('quote') or str(ev)
                er = existing_extraction_reviews.get(ext.id)
                extractions_list.append({
                    "extraction_id": ext.id,
                    "category": ext.category or "Parameter",
                    "parameter_name": getattr(ext.extraction_definition, 'name', None) or ext.category or "Parameter",
                    "extracted_value": val,
                    "uncertainty": str(unc) if unc else None,
                    "method": str(meth) if meth else None,
                    "text_evidence": str(ev) if ev else None,
                    "page_number": fd.get('page') or fd.get('page_number'),
                    "status": er.action if er else "pending",
                })
            first_er = ExtractionReview.objects.filter(sample_cohort=cohort, paper=paper, reviewer=request.user).first()
            if first_er:
                is_reviewed = True
                reviewer_decision = first_er.action
                reviewer_note = first_er.reviewer_notes
                reviewed_at = first_er.submitted_at
        else:
            existing_review = ScreeningReview.objects.filter(
                sample_cohort=cohort,
                paper=paper,
                reviewer=request.user,
                stage=stage_review
            ).first()
            if existing_review:
                is_reviewed = True
                reviewer_decision = (
                    'agree' if ((existing_review.decision == 'include' and ai_is_included) or (existing_review.decision == 'exclude' and not ai_is_included))
                    else ('override_include' if existing_review.decision == 'include' else 'override_exclude')
                )
                exclusion_reason = existing_review.exclusion_reason
                reviewer_note = existing_review.reviewer_notes
                reviewed_at = existing_review.submitted_at
                if existing_review.evidence_quotes:
                    first_q = existing_review.evidence_quotes[0]
                    if isinstance(first_q, dict):
                        evidence_citation = first_q.get('quote')
                    elif isinstance(first_q, str):
                        evidence_citation = first_q

        # Navigation: calculate prev and next papers in the cohort
        sampled_ids = list(cohort.sampled_papers.order_by('created_at', 'id').values_list('id', flat=True))
        try:
            curr_idx = sampled_ids.index(paper.id)
            prev_id = sampled_ids[curr_idx - 1] if curr_idx > 0 else None
            next_id = sampled_ids[curr_idx + 1] if curr_idx < len(sampled_ids) - 1 else None
            index_1_based = curr_idx + 1
        except ValueError:
            prev_id = next_id = None
            index_1_based = 1

        has_pdf = bool(getattr(paper, 'original_pdf_path', None) or getattr(paper, 'pdf_path', None))
        has_full_text = has_pdf or bool(getattr(paper, 'converted_md_path', None) or getattr(paper, 'full_text_path', None))
        pdf_url = f"/api/papers/{paper.id}/pdf/" if has_pdf else None

        meta = paper.meta or {}
        journal = getattr(paper, 'journal', None) or meta.get('journal') or meta.get('venue')
        publication_year = getattr(paper, 'publication_year', None) or meta.get('publication_year') or meta.get('year')

        payload = {
            "paper_id": paper.id,
            "cohort_id": cohort.id,
            "title": paper.title,
            "authors": paper.authors,
            "journal": journal,
            "publication_year": publication_year,
            "doi": paper.doi,
            "pdf_url": pdf_url,
            "has_full_text": has_full_text,
            "abstract": paper.abstract,
            "ai_decision": 'include' if ai_is_included else 'exclude',
            "ai_confidence": ai_confidence,
            "ai_reasoning": ai_reasoning,
            "matched_criteria": matched_criteria,
            "evidence_quotes": evidence_quotes,
            "is_reviewed": is_reviewed,
            "reviewer_decision": reviewer_decision,
            "exclusion_reason": exclusion_reason,
            "reviewer_note": reviewer_note,
            "evidence_citation": evidence_citation,
            "reviewed_at": reviewed_at,
            "current_index": index_1_based,
            "total_count": len(sampled_ids),
            "prev_paper_id": prev_id,
            "next_paper_id": next_id,
            "extractions": extractions_list,
        }

        serializer = AuditPaperDetailSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SubmitScreeningReviewView(APIView):
    """
    Submits an individual blind review vote for a paper within an audit cohort.
    Automatically calculates consensus and auto-advances.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, cohort_id, paper_id):
        cohort = get_object_or_404(AuditSampleCohort.objects.select_related('pipeline_run', 'config__workspace'), pk=cohort_id)
        denied = check_slr_workspace_access(request.user, cohort.config.workspace)
        if denied:
            return denied
        paper = get_object_or_404(Paper, pk=paper_id)
        if not cohort.sampled_papers.filter(pk=paper.pk).exists():
            return Response({"error": "Paper is not part of this audit cohort."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SubmitScreeningReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        exclusion_reason = serializer.validated_data.get('exclusion_reason')
        reviewer_note = serializer.validated_data.get('reviewer_note')
        evidence_citation = serializer.validated_data.get('evidence_citation')
        time_spent_seconds = serializer.validated_data.get('time_spent_seconds', 0)

        stage_review = 'abstract' if cohort.stage == 'abstract_screening' else 'full_text'

        # Map UI action to decision
        metric = PaperMetric.objects.filter(paper=paper, pipeline_run=cohort.pipeline_run).first()
        ai_decision = 'include' if metric and metric.screening_status in ('abstract_passed', 'full_text_passed', 'accepted') else 'exclude'

        if action == 'agree':
            decision = ai_decision
        elif action == 'override_include':
            decision = 'include'
        elif action == 'override_exclude':
            decision = 'exclude'
        else:
            decision = 'uncertain'

        evidence_quotes = []
        if evidence_citation:
            evidence_quotes.append({
                "quote": evidence_citation,
                "annotation_type": "reviewer_override_justification",
                "page_number": 1
            })

        review = ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=request.user,
            stage=stage_review,
            decision=decision,
            exclusion_reason=exclusion_reason,
            evidence_quotes=evidence_quotes,
            reviewer_notes=reviewer_note,
            time_spent_seconds=time_spent_seconds
        )

        cohort.refresh_from_db()

        # Find next unreviewed paper in cohort for smooth auto-advance
        sampled_ids = list(cohort.sampled_papers.order_by('created_at', 'id').values_list('id', flat=True))
        reviewed_ids = set(
            ScreeningReview.objects.filter(
                sample_cohort=cohort,
                reviewer=request.user,
                stage=stage_review
            ).values_list('paper_id', flat=True)
        )
        next_unreviewed_id = next((pid for pid in sampled_ids if pid not in reviewed_ids), None)

        return Response({
            "status": "reviewed",
            "review_id": review.id,
            "decision": decision,
            "is_cohort_complete": cohort.is_audit_complete,
            "next_unreviewed_paper_id": next_unreviewed_id,
            "next_paper_id": next_unreviewed_id,
            "pipeline_resumed": cohort.is_audit_complete,
            "success": True,
            "completed_count": len(reviewed_ids),
            "total_count": len(sampled_ids)
        }, status=status.HTTP_200_OK)


class SubmitExtractionReviewView(APIView):
    """Submits audit decisions (verify, modify, reject) on extracted parameters."""
    permission_classes = [IsAuthenticated]

    def post(self, request, cohort_id, extraction_id):
        cohort = get_object_or_404(AuditSampleCohort.objects.select_related('pipeline_run', 'config__workspace'), pk=cohort_id)
        denied = check_slr_workspace_access(request.user, cohort.config.workspace)
        if denied:
            return denied
        extraction = get_object_or_404(Extraction, pk=extraction_id)
        if not cohort.sampled_papers.filter(pk=extraction.paper_id).exists():
            return Response({"error": "Extraction does not belong to a paper in this audit cohort."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SubmitExtractionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        corrected_fields = serializer.validated_data.get('corrected_fields')
        verified_evidence_quotes = serializer.validated_data.get('verified_evidence_quotes', [])
        reviewer_notes = serializer.validated_data.get('reviewer_notes')
        time_spent_seconds = serializer.validated_data.get('time_spent_seconds', 0)

        review, _ = ExtractionReview.objects.update_or_create(
            sample_cohort=cohort,
            extraction=extraction,
            reviewer=request.user,
            defaults={
                'paper': extraction.paper,
                'action': action,
                'original_fields': extraction.fields_data,
                'corrected_fields': corrected_fields,
                'verified_evidence_quotes': verified_evidence_quotes,
                'reviewer_notes': reviewer_notes,
                'time_spent_seconds': time_spent_seconds
            }
        )

        # Propagate auditor corrections to extraction fields_data
        fields_data = dict(extraction.fields_data or {})
        if action == 'modify' and corrected_fields:
            if '_original_ai_fields' not in fields_data:
                fields_data['_original_ai_fields'] = dict(extraction.fields_data or {})
            fields_data.update(corrected_fields)
            fields_data['_audit_status'] = 'modified'
            extraction.fields_data = fields_data
            extraction.save(update_fields=['fields_data'])
        elif action == 'reject':
            fields_data['_audit_status'] = 'rejected'
            extraction.fields_data = fields_data
            extraction.save(update_fields=['fields_data'])
        elif action == 'verify':
            fields_data['_audit_status'] = 'verified'
            extraction.fields_data = fields_data
            extraction.save(update_fields=['fields_data'])

        ConsensusService.check_cohort_completion(cohort)
        cohort.refresh_from_db()

        return Response({
            "success": True,
            "review_id": review.id,
            "is_cohort_complete": cohort.is_audit_complete
        }, status=status.HTTP_200_OK)


class DisputeListView(APIView):
    """Lists disputes requiring Senior Arbiter ruling."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_data.get('status', 'pending') if hasattr(request, 'query_data') else request.GET.get('status', 'pending')
        disputes = AdjudicationDispute.objects.filter(status=status_filter).select_related('paper', 'arbiter', 'sample_cohort__config__workspace')
        if not request.user.is_superuser:
            from research_intelligence.models import WorkspaceMember
            user_ws_ids = set(WorkspaceMember.objects.filter(user=request.user).values_list('workspace_id', flat=True))
            workspaces_with_members = set(WorkspaceMember.objects.values_list('workspace_id', flat=True))
            from django.db.models import Q
            disputes = disputes.filter(
                Q(sample_cohort__config__workspace_id__in=user_ws_ids) |
                ~Q(sample_cohort__config__workspace_id__in=workspaces_with_members)
            ).distinct()
        serializer = AdjudicationDisputeSerializer(disputes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ResolveDisputeView(APIView):
    """Senior Arbiter ruling resolution endpoint."""
    permission_classes = [IsAuthenticated]

    def post(self, request, dispute_id):
        dispute = get_object_or_404(AdjudicationDispute.objects.select_related('sample_cohort__config__workspace'), pk=dispute_id)
        workspace = dispute.sample_cohort.config.workspace
        denied = check_slr_workspace_access(request.user, workspace)
        if denied:
            return denied

        # Role verification: Only designated arbiter, workspace admin/owner, or superuser can resolve
        designated = dispute.sample_cohort.config.designated_arbiter
        is_designated = (designated and designated == request.user)
        is_admin = False
        if not request.user.is_superuser:
            from research_intelligence.models import WorkspaceMember
            mem = WorkspaceMember.objects.filter(workspace=workspace, user=request.user).first()
            if mem and mem.role in ('admin', 'owner'):
                is_admin = True
            if not is_designated and not is_admin:
                return Response(
                    {"error": "Only the designated arbiter or workspace admin can resolve disputes."},
                    status=status.HTTP_403_FORBIDDEN
                )

        if dispute.status == 'resolved':
            return Response(
                {"error": "This dispute has already been resolved and cannot be re-adjudicated."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ResolveDisputeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ConsensusService.resolve_dispute(
            dispute=dispute,
            arbiter=request.user,
            final_decision=serializer.validated_data['final_decision'],
            resolution_rationale=serializer.validated_data['resolution_rationale'],
            final_exclusion_reason=serializer.validated_data.get('final_exclusion_reason')
        )

        return Response({
            "success": True,
            "dispute_id": dispute.id,
            "status": "resolved",
            "final_decision": dispute.final_decision
        }, status=status.HTTP_200_OK)


class ResumePipelineView(APIView):
    """Resumes a paused SLR pipeline run once audit is verified."""
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        pipeline_run = get_object_or_404(PipelineRun.objects.select_related('workspace'), pk=run_id)
        denied = check_slr_workspace_access(request.user, pipeline_run.workspace, require_admin=True)
        if denied:
            return denied
        res = resume_slr_pipeline_run(pipeline_run)
        if not res.get("resumed"):
            return Response(res, status=status.HTTP_400_BAD_REQUEST)
        return Response(res, status=status.HTTP_200_OK)


class PRISMAMetricsView(APIView):
    """Returns PRISMA 2020 statement flow metrics for pipeline run."""
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        pipeline_run = get_object_or_404(PipelineRun.objects.select_related('workspace'), pk=run_id)
        denied = check_slr_workspace_access(request.user, pipeline_run.workspace)
        if denied:
            return denied
        metrics = MetricsService.compute_prisma_metrics(pipeline_run)
        serializer = SLRPRISMAMetricsSerializer(metrics)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RiskOfBiasListView(APIView):
    """Returns Cochrane Risk of Bias assessments for included studies."""
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        pipeline_run = get_object_or_404(PipelineRun.objects.select_related('workspace'), pk=run_id)
        denied = check_slr_workspace_access(request.user, pipeline_run.workspace)
        if denied:
            return denied
        assessments = RiskOfBiasAssessment.objects.filter(pipeline_run=pipeline_run).select_related('paper')
        if not assessments.exists():
            slr_cfg = getattr(pipeline_run.workspace, 'slr_config', None)
            if slr_cfg and slr_cfg.enable_rob_assessment:
                from slr_review.services.rob_service import RiskOfBiasService
                included_papers = pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted'])
                for p in included_papers:
                    RiskOfBiasService.assess_paper_rob(p, pipeline_run, framework=slr_cfg.rob_framework)
                assessments = RiskOfBiasAssessment.objects.filter(pipeline_run=pipeline_run).select_related('paper')
        serializer = RiskOfBiasAssessmentSerializer(assessments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WorkspaceSLRConfigView(APIView):
    """Reads or updates SLR policy configuration for a given workspace."""
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws = get_object_or_404(Workspace, pk=workspace_id)
        denied = check_slr_workspace_access(request.user, ws)
        if denied:
            return denied
        config, _ = SLRWorkspaceConfig.objects.get_or_create(workspace=ws)
        serializer = SLRWorkspaceConfigSerializer(config)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, workspace_id):
        ws = get_object_or_404(Workspace, pk=workspace_id)
        denied = check_slr_workspace_access(request.user, ws, require_admin=True)
        if denied:
            return denied
        config, _ = SLRWorkspaceConfig.objects.get_or_create(workspace=ws)
        serializer = SLRWorkspaceConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
