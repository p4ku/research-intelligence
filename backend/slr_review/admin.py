from django.contrib import admin
from .models import (
    SLRWorkspaceConfig,
    SLRProtocol,
    ProtocolAmendment,
    AuditSampleCohort,
    ScreeningReview,
    ExtractionReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
    SLRPRISMAMetrics,
    SearchQueryRecord,
    MetaAnalysisOutcomeData,
)


@admin.register(SLRWorkspaceConfig)
class SLRWorkspaceConfigAdmin(admin.ModelAdmin):
    list_display = (
        'workspace',
        'checkpoint_gate_mode',
        'screening_quorum_size',
        'require_blind_review',
        'sampling_mode',
        'enable_rob_assessment',
        'designated_arbiter',
        'created_at',
    )
    list_filter = ('checkpoint_gate_mode', 'sampling_mode', 'enable_rob_assessment', 'require_blind_review')
    search_fields = ('workspace__name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


class ProtocolAmendmentInline(admin.TabularInline):
    model = ProtocolAmendment
    extra = 0
    readonly_fields = ('created_at',)


class SearchQueryRecordInline(admin.TabularInline):
    model = SearchQueryRecord
    extra = 0
    readonly_fields = ('executed_at',)


@admin.register(SLRProtocol)
class SLRProtocolAdmin(admin.ModelAdmin):
    list_display = ('title', 'workspace', 'version', 'is_locked', 'prospero_registration_id', 'created_by', 'created_at')
    list_filter = ('is_locked', 'workspace')
    search_fields = ('title', 'review_question', 'prospero_registration_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ProtocolAmendmentInline, SearchQueryRecordInline]


@admin.register(ProtocolAmendment)
class ProtocolAmendmentAdmin(admin.ModelAdmin):
    list_display = ('protocol', 'amendment_number', 'approved_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('protocol__title', 'rationale')
    readonly_fields = ('id', 'created_at')


@admin.register(AuditSampleCohort)
class AuditSampleCohortAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'stage', 'sampled_count', 'total_pool_count', 'is_audit_complete', 'completed_at', 'created_at')
    list_filter = ('stage', 'is_audit_complete')
    search_fields = ('pipeline_run__name', 'config__workspace__name')
    readonly_fields = ('id', 'created_at')
    filter_horizontal = ('sampled_papers',)

    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = "Cohort ID"


@admin.register(ScreeningReview)
class ScreeningReviewAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'paper_title', 'stage', 'decision', 'exclusion_reason', 'submitted_at')
    list_filter = ('stage', 'decision', 'submitted_at')
    search_fields = ('reviewer__username', 'paper__title', 'exclusion_reason', 'reviewer_notes')
    readonly_fields = ('id', 'submitted_at')

    def paper_title(self, obj):
        return obj.paper.title[:40] if obj.paper else '-'
    paper_title.short_description = "Paper"


@admin.register(ExtractionReview)
class ExtractionReviewAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'paper_title', 'action', 'time_spent_seconds', 'submitted_at')
    list_filter = ('action', 'submitted_at')
    search_fields = ('reviewer__username', 'paper__title', 'reviewer_notes')
    readonly_fields = ('id', 'submitted_at')

    def paper_title(self, obj):
        return obj.paper.title[:40] if obj.paper else '-'
    paper_title.short_description = "Paper"


@admin.register(AdjudicationDispute)
class AdjudicationDisputeAdmin(admin.ModelAdmin):
    list_display = ('paper_title', 'stage', 'status', 'final_decision', 'arbiter', 'resolved_at', 'created_at')
    list_filter = ('status', 'stage', 'final_decision')
    search_fields = ('paper__title', 'resolution_rationale')
    readonly_fields = ('id', 'created_at')

    def paper_title(self, obj):
        return obj.paper.title[:40] if obj.paper else '-'
    paper_title.short_description = "Paper"


@admin.register(RiskOfBiasAssessment)
class RiskOfBiasAssessmentAdmin(admin.ModelAdmin):
    list_display = ('paper_title', 'framework', 'overall_bias', 'traffic_light_color', 'is_human_verified', 'verified_by')
    list_filter = ('framework', 'overall_bias', 'traffic_light_color', 'is_human_verified')
    search_fields = ('paper__title', 'human_notes')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def paper_title(self, obj):
        return obj.paper.title[:40] if obj.paper else '-'
    paper_title.short_description = "Paper"


@admin.register(SLRPRISMAMetrics)
class SLRPRISMAMetricsAdmin(admin.ModelAdmin):
    list_display = (
        'pipeline_run',
        'records_identified_total',
        'duplicates_removed',
        'records_screened_abstract',
        'full_text_assessed',
        'studies_included_synthesis',
        'human_inter_rater_kappa',
        'ai_vs_human_kappa',
        'generated_at',
    )
    search_fields = ('pipeline_run__name', 'pipeline_run__id')
    readonly_fields = ('id', 'generated_at')


@admin.register(SearchQueryRecord)
class SearchQueryRecordAdmin(admin.ModelAdmin):
    list_display = ('database_name', 'protocol', 'total_yield', 'executed_at')
    list_filter = ('database_name', 'executed_at')
    search_fields = ('database_name', 'raw_query_string', 'protocol__title')
    readonly_fields = ('id', 'executed_at')


@admin.register(MetaAnalysisOutcomeData)
class MetaAnalysisOutcomeDataAdmin(admin.ModelAdmin):
    list_display = ('outcome_name', 'paper_title', 'outcome_type', 'effect_size_estimate', 'p_value', 'created_at')
    list_filter = ('outcome_type', 'created_at')
    search_fields = ('outcome_name', 'paper__title')
    readonly_fields = ('id', 'created_at')

    def paper_title(self, obj):
        return obj.paper.title[:40] if obj.paper else '-'
    paper_title.short_description = "Paper"
