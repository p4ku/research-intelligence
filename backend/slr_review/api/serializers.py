from rest_framework import serializers
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
from research_intelligence.models import Paper, PaperMetric


class SLRWorkspaceConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLRWorkspaceConfig
        fields = '__all__'


class SLRProtocolSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLRProtocol
        fields = '__all__'


class AuditQueueItemSerializer(serializers.Serializer):
    cohort_id = serializers.UUIDField()
    pipeline_run_id = serializers.UUIDField()
    workspace_id = serializers.UUIDField()
    workspace_name = serializers.CharField()
    briefing_name = serializers.CharField()
    gate = serializers.CharField()
    assigned_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    remaining_count = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class AuditPaperDetailSerializer(serializers.Serializer):
    paper_id = serializers.UUIDField()
    cohort_id = serializers.UUIDField()
    title = serializers.CharField()
    authors = serializers.CharField()
    journal = serializers.CharField(allow_null=True)
    publication_year = serializers.IntegerField(allow_null=True)
    doi = serializers.CharField(allow_null=True)
    pdf_url = serializers.CharField(allow_null=True)
    has_full_text = serializers.BooleanField()
    abstract = serializers.CharField(allow_null=True)

    # AI Decision & Grounding Evidence
    ai_decision = serializers.ChoiceField(choices=['include', 'exclude'])
    ai_confidence = serializers.FloatField()
    ai_reasoning = serializers.CharField()
    matched_criteria = serializers.ListField(child=serializers.CharField(), default=list)
    evidence_quotes = serializers.ListField(child=serializers.DictField(), default=list)

    # Human Review State for current user
    is_reviewed = serializers.BooleanField()
    reviewer_decision = serializers.CharField(allow_null=True)
    exclusion_reason = serializers.CharField(allow_null=True)
    reviewer_note = serializers.CharField(allow_null=True)
    evidence_citation = serializers.CharField(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)

    # Navigation Context
    current_index = serializers.IntegerField()
    total_count = serializers.IntegerField()
    prev_paper_id = serializers.UUIDField(allow_null=True)
    next_paper_id = serializers.UUIDField(allow_null=True)

    # Parameter Extractions (Gate 2 / Extraction Audit)
    extractions = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class SubmitScreeningReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['agree', 'override_include', 'override_exclude'])
    exclusion_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reviewer_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    evidence_citation = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    time_spent_seconds = serializers.IntegerField(required=False, default=0)

    def validate(self, attrs):
        action = attrs.get('action')
        if action == 'override_exclude' and not attrs.get('exclusion_reason'):
            raise serializers.ValidationError({"exclusion_reason": "Exclusion reason is required when overriding to Exclude."})
        return attrs


class SubmitExtractionReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['verify', 'modify', 'reject'])
    corrected_fields = serializers.DictField(required=False, allow_null=True)
    verified_evidence_quotes = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    reviewer_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    time_spent_seconds = serializers.IntegerField(required=False, default=0)


class AdjudicationDisputeSerializer(serializers.ModelSerializer):
    paper_title = serializers.CharField(source='paper.title', read_only=True)
    paper_doi = serializers.CharField(source='paper.doi', read_only=True)

    class Meta:
        model = AdjudicationDispute
        fields = '__all__'


class ResolveDisputeSerializer(serializers.Serializer):
    final_decision = serializers.ChoiceField(choices=['include', 'exclude'])
    resolution_rationale = serializers.CharField()
    final_exclusion_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class RiskOfBiasAssessmentSerializer(serializers.ModelSerializer):
    paper_title = serializers.CharField(source='paper.title', read_only=True)
    paper_doi = serializers.CharField(source='paper.doi', read_only=True, default='')
    paper_authors = serializers.CharField(source='paper.authors', read_only=True, default='')

    class Meta:
        model = RiskOfBiasAssessment
        fields = '__all__'


class SLRPRISMAMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLRPRISMAMetrics
        fields = '__all__'
