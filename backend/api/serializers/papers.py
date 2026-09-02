from rest_framework import serializers
from research_intelligence.models import Paper, PaperMetric

class PaperMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperMetric
        fields = '__all__'

class PaperSerializer(serializers.ModelSerializer):
    pipeline_run = serializers.SerializerMethodField()
    pipeline_run_id = serializers.SerializerMethodField()
    run_id = serializers.SerializerMethodField()
    metrics = PaperMetricSerializer(many=True, read_only=True)
    signal_score = serializers.SerializerMethodField()
    signal_score_details = serializers.SerializerMethodField()
    screening_status = serializers.SerializerMethodField()
    screening_reasoning = serializers.SerializerMethodField()
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
                req_pr = (
                    req.query_params.get('pipeline_run')
                    or req.query_params.get('pipeline_run_id')
                    or req.query_params.get('run_id')
                )
                if req_pr:
                    target_pr = str(req_pr).replace('-', '').lower()
            if not target_pr and self.context.get('pipeline_run_id'):
                target_pr = str(self.context['pipeline_run_id']).replace('-', '').lower()

        if not target_pr:
            ann_pr = getattr(obj, 'annotated_pipeline_run_id', None)
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

    def get_pipeline_run_id(self, obj):
        m = self._get_target_metric(obj)
        return str(m.pipeline_run_id) if (m and m.pipeline_run_id) else None

    def get_run_id(self, obj):
        return self.get_pipeline_run_id(obj)

    def get_pipeline_run(self, obj):
        return self.get_pipeline_run_id(obj)

    def get_screening_status(self, obj):
        m = self._get_target_metric(obj)
        return m.screening_status if m else 'pending'

    def get_screening_reasoning(self, obj):
        m = self._get_target_metric(obj)
        return m.screening_reasoning if m else None

    def get_signal_score(self, obj):
        m = self._get_target_metric(obj)
        return m.signal_score if m else None

    def get_signal_score_details(self, obj):
        m = self._get_target_metric(obj)
        return m.signal_score_details if m else {}

    def get_is_evaluation_benchmark(self, obj):
        m = self._get_target_metric(obj)
        return m.is_evaluation_benchmark if m else False

    def get_evaluation_label(self, obj):
        m = self._get_target_metric(obj)
        return m.evaluation_label if m else None

    class Meta:
        model = Paper
        fields = [
            'id', 'workspace', 'pipeline_run', 'pipeline_run_id', 'run_id',
            'hash_id', 'doi', 'arxiv_id', 'title', 'authors', 'abstract',
            'source_database', 'original_pdf_path', 'converted_md_path',
            'screening_status', 'screening_reasoning', 'is_evaluation_benchmark',
            'evaluation_label', 'signal_score', 'signal_score_details',
            'metrics', 'created_at'
        ]
