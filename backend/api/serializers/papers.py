from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from research_intelligence.models import Paper, PaperMetric

class PaperMetricSerializer(serializers.ModelSerializer):
    pipeline_run = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_pipeline_run(self, obj):
        if obj.pipeline_run_id:
            return str(obj.pipeline_run_id)
        if obj.workspace_id:
            from research_intelligence.models import PipelineRun
            run_id = (
                PipelineRun.objects.filter(workspace_id=obj.workspace_id)
                .exclude(status__in=['failed', 'aborted'])
                .order_by('-started_at', '-id')
                .values_list('id', flat=True)
                .first()
            )
            if not run_id:
                run_id = (
                    PipelineRun.objects.filter(workspace_id=obj.workspace_id)
                    .order_by('-started_at', '-id')
                    .values_list('id', flat=True)
                    .first()
                )
            if run_id:
                return str(run_id)
        return None

    class Meta:
        model = PaperMetric
        fields = '__all__'

class PaperSerializer(serializers.ModelSerializer):
    pipeline_run = serializers.SerializerMethodField()
    pipeline_run_id = serializers.SerializerMethodField()
    run_id = serializers.SerializerMethodField()
    pipeline_run_name = serializers.SerializerMethodField()
    published_date = serializers.SerializerMethodField()
    metrics = PaperMetricSerializer(many=True, read_only=True)
    signal_score = serializers.SerializerMethodField()
    signal_score_details = serializers.SerializerMethodField()
    screening_status = serializers.SerializerMethodField()
    screening_reasoning = serializers.SerializerMethodField()
    abstract_screening_reasoning = serializers.SerializerMethodField()
    full_text_screening_reasoning = serializers.SerializerMethodField()
    is_evaluation_benchmark = serializers.SerializerMethodField()
    evaluation_label = serializers.SerializerMethodField()

    def _get_workspace_latest_run_id(self, workspace_id):
        if not workspace_id:
            return None
        if not hasattr(self, '_ws_latest_run_cache'):
            self._ws_latest_run_cache = {}
        if workspace_id in self._ws_latest_run_cache:
            return self._ws_latest_run_cache[workspace_id]

        from research_intelligence.models import PipelineRun
        run_id = (
            PipelineRun.objects.filter(workspace_id=workspace_id)
            .exclude(status__in=['failed', 'aborted'])
            .order_by('-started_at', '-id')
            .values_list('id', flat=True)
            .first()
        )
        if not run_id:
            run_id = (
                PipelineRun.objects.filter(workspace_id=workspace_id)
                .order_by('-started_at', '-id')
                .values_list('id', flat=True)
                .first()
            )
        self._ws_latest_run_cache[workspace_id] = run_id
        return run_id

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
            if not target_pr and self.context.get('pipeline_run'):
                target_pr = str(self.context['pipeline_run']).replace('-', '').lower()
            if not target_pr and self.context.get('pipeline_run_id'):
                target_pr = str(self.context['pipeline_run_id']).replace('-', '').lower()

        if not target_pr:
            ann_pr = getattr(obj, 'annotated_pipeline_run', None) or getattr(obj, 'annotated_pipeline_run_id', None)
            if ann_pr:
                target_pr = str(ann_pr).replace('-', '').lower()

        # If still no target_pr, check if workspace has a latest run
        if not target_pr and obj.workspace_id and metrics:
            latest_id = self._get_workspace_latest_run_id(obj.workspace_id)
            if latest_id:
                target_pr = str(latest_id).replace('-', '').lower()

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
        if m and m.pipeline_run_id:
            return str(m.pipeline_run_id)

        pr = getattr(obj, 'pipeline_run', None)
        if pr:
            pr_id = getattr(pr, 'id', pr)
            if pr_id:
                return str(pr_id)

        latest_run_id = self._get_workspace_latest_run_id(obj.workspace_id)
        if latest_run_id:
            return str(latest_run_id)

        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_pipeline_run_id(self, obj):
        return self.get_pipeline_run(obj)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_run_id(self, obj):
        return self.get_pipeline_run(obj)

    @extend_schema_field(serializers.CharField())
    def get_screening_status(self, obj):
        m = self._get_target_metric(obj)
        return m.screening_status if m else 'pending'

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_screening_reasoning(self, obj):
        m = self._get_target_metric(obj)
        if m:
            return m.screening_reasoning or m.full_text_screening_reasoning or m.abstract_screening_reasoning
        return None

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

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_published_date(self, obj):
        meta = getattr(obj, 'meta', None) or {}
        for k in ('published', 'publication_date', 'published_date', 'date'):
            val = meta.get(k)
            if val:
                return str(val)[:10]
        if obj.created_at:
            return obj.created_at.strftime('%Y-%m-%d')
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_pipeline_run_name(self, obj):
        m = self._get_target_metric(obj)
        if m and hasattr(m, '_state') and 'pipeline_run' in m._state.fields_cache:
            pr = m._state.fields_cache['pipeline_run']
            if pr:
                return pr.name or f"Briefing {pr.run_date}"
        if hasattr(obj, '_state') and 'pipeline_run' in obj._state.fields_cache:
            pr = obj._state.fields_cache['pipeline_run']
            if pr:
                return pr.name or f"Briefing {pr.run_date}"
        if hasattr(obj, '_pipeline_run') and obj._pipeline_run is not None:
            return getattr(obj._pipeline_run, 'name', None) or f"Briefing {getattr(obj._pipeline_run, 'run_date', '')}"
        return None

    class Meta:
        model = Paper
        fields = [
            'id', 'workspace', 'pipeline_run', 'pipeline_run_id', 'run_id', 'pipeline_run_name',
            'hash_id', 'doi', 'arxiv_id', 'title', 'authors', 'abstract', 'published_date',
            'source_database', 'original_pdf_path', 'converted_md_path',
            'screening_status', 'screening_reasoning',
            'abstract_screening_reasoning', 'full_text_screening_reasoning',
            'is_evaluation_benchmark', 'evaluation_label', 'signal_score', 'signal_score_details',
            'metrics', 'created_at'
        ]
