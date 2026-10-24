from django.urls import path
from .views import (
    AuditQueueListView,
    AuditCohortDetailView,
    AuditPaperDetailView,
    SubmitScreeningReviewView,
    SubmitExtractionReviewView,
    DisputeListView,
    ResolveDisputeView,
    ResumePipelineView,
    PRISMAMetricsView,
    RiskOfBiasListView,
    WorkspaceSLRConfigView,
)

urlpatterns = [
    # 1. Audit Queue & Reviewer Workflows
    path('cohorts/my-queue/', AuditQueueListView.as_view(), name='slr-audit-my-queue'),
    path('cohorts/<uuid:cohort_id>/', AuditCohortDetailView.as_view(), name='slr-cohort-detail'),
    path('cohorts/<uuid:cohort_id>/papers/<uuid:paper_id>/', AuditPaperDetailView.as_view(), name='slr-paper-detail'),
    path('cohorts/<uuid:cohort_id>/papers/<uuid:paper_id>/review/', SubmitScreeningReviewView.as_view(), name='slr-review-submit'),
    path('cohorts/<uuid:cohort_id>/extractions/<uuid:extraction_id>/audit/', SubmitExtractionReviewView.as_view(), name='slr-extraction-audit'),

    # 2. Senior Arbiter Adjudication
    path('disputes/', DisputeListView.as_view(), name='slr-disputes-list'),
    path('disputes/<uuid:dispute_id>/resolve/', ResolveDisputeView.as_view(), name='slr-dispute-resolve'),

    # 3. Pipeline Lifecycle & Synthesis Deliverables
    path('runs/<uuid:run_id>/resume/', ResumePipelineView.as_view(), name='slr-run-resume'),
    path('runs/<uuid:run_id>/prisma/', PRISMAMetricsView.as_view(), name='slr-run-prisma'),
    path('runs/<uuid:run_id>/rob/', RiskOfBiasListView.as_view(), name='slr-run-rob'),

    # 4. Workspace Policies
    path('workspaces/<uuid:workspace_id>/config/', WorkspaceSLRConfigView.as_view(), name='slr-workspace-config'),
]
