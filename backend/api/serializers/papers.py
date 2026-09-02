from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from research_intelligence.models import Paper, PaperMetric

class PaperMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperMetric
        fields = '__all__'

class PaperSerializer(serializers.ModelSerializer):
    pipeline_run = serializers.SerializerMethodField()
    metrics = PaperMetricSerializer(many=True, read_only=True)
    signal_score = serializers.SerializerMethodField()
    signal_score_details = serializers.SerializerMethodField()
    screening_status = serializers.SerializerMethodField()
    screening_reasoning = serializers.SerializerMethodField()
    abstract_screening_reasoning = serializers.SerializerMethodField()
    full_text_screening_reasoning = serializers.SerializerMethodField()
    is_evaluation_benchmark = serializers.SerializerMethodField()
    evaluation_label = serializers.SerializerMethodField()

    def _get_target_metric(self, obj):
        if hasattr(obj, '_cached_target_metric'):
            return obj._cached_target_metric

        metrics = list(obj.metrics.all())
        target_pr = None

        if hasattr(self, 'context') and self.context:
            req = self.context.get('request')
            if req and hasattr(req, 'query_params'):
                req_pr = req.query_params.get('pipeline_run')
                if req_pr:
                    target_pr = str(req_pr).replace('-', '').lower()
            if not target_pr and self.context.get('pipeline_run'):
                target_pr = str(self.context['pipeline_run']).replace('-', '').lower()

        if not target_pr:
            ann_pr = getattr(obj, 'annotated_pipeline_run', None)
            if ann_pr:
                target_pr = str(ann_pr).replace('-', '').lower()

        if target_pr and metrics:
            m = next((m for m in metrics if str(m.pipeline_run_id).replace('-', '').lower() == target_pr), None)
            if m:
                obj._cached_target_metric = m
                return m

        if metrics:
            m = sorted(metrics, key=lambda x: x.created_at, reverse=True)[0]
            obj._cached_target_metric = m
            return m

        obj._cached_target_metric = None
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_pipeline_run(self, obj):
        m = self._get_target_metric(obj)
        return str(m.pipeline_run_id) if (m and m.pipeline_run_id) else None

    @extend_schema_field(serializers.CharField())
    def get_screening_status(self, obj):
        m = self._get_target_metric(obj)
        return m.screening_status if m else 'pending'

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_screening_reasoning(self, obj):
        m = self._get_target_metric(obj)
        return m.screening_reasoning if m else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_abstract_screening_reasoning(self, obj):
        m = self._get_target_metric(obj)
        return m.abstract_screening_reasoning if m else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_full_text_screening_reasoning(self, obj):
        m = self._get_target_metric(obj)
        return m.full_text_screening_reasoning if m else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_signal_score(self, obj):
        m = self._get_target_metric(obj)
        return m.signal_score if m else None

    @extend_schema_field(serializers.JSONField())
    def get_signal_score_details(self, obj):
        m = self._get_target_metric(obj)
        return m.signal_score_details if m else {}

    @extend_schema_field(serializers.BooleanField())
    def get_is_evaluation_benchmark(self, obj):
        m = self._get_target_metric(obj)
        return m.is_evaluation_benchmark if m else False

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_evaluation_label(self, obj):
        m = self._get_target_metric(obj)
        return m.evaluation_label if m else None

    class Meta:
        model = Paper
        fields = [
            'id', 'workspace', 'pipeline_run',
            'hash_id', 'doi', 'arxiv_id', 'title', 'authors', 'abstract',
            'source_database', 'original_pdf_path', 'converted_md_path',
            'screening_status', 'screening_reasoning',
            'abstract_screening_reasoning', 'full_text_screening_reasoning',
            'is_evaluation_benchmark', 'evaluation_label', 'signal_score', 'signal_score_details',
            'metrics', 'created_at'
        ]
