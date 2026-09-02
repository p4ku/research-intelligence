from rest_framework import serializers
from research_intelligence.models import PipelineRun, ComponentRun, Paper, Extraction, PaperMetric
from mcp_server.tools.pipeline_runs.status import _get_run_storage_stats


class ComponentRunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.FloatField(read_only=True)
    execution_time_display = serializers.CharField(read_only=True)

    class Meta:
        model = ComponentRun
        fields = [
            'id',
            'pipeline_run',
            'step_type',
            'component_name',
            'status',
            'celery_task_id',
            'raw_storage_path',
            'input_params',
            'metrics',
            'output_data',
            'error_message',
            'started_at',
            'completed_at',
            'duration_seconds',
            'execution_time_display',
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'duration_seconds', 'execution_time_display']


class PipelineRunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.FloatField(read_only=True)
    execution_time_display = serializers.CharField(read_only=True)
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    triggered_by_username = serializers.CharField(source='triggered_by.username', read_only=True, default=None)
    schedule_name = serializers.CharField(source='schedule.name', read_only=True, default=None)

    class Meta:
        model = PipelineRun
        fields = [
            'id',
            'workspace',
            'workspace_name',
            'schedule',
            'schedule_name',
            'run_date',
            'status',
            'current_stage',
            'total_papers_fetched',
            'total_papers_passed_screening',
            'tokens_in',
            'tokens_out',
            'tokens_consumed',
            'usd_cost',
            'triggered_by',
            'triggered_by_username',
            'reprocess_existing',
            'status_message',
            'started_at',
            'completed_at',
            'duration_seconds',
            'execution_time_display',
        ]
        read_only_fields = [
            'id',
            'run_date',
            'started_at',
            'completed_at',
            'duration_seconds',
            'execution_time_display',
            'workspace_name',
            'triggered_by_username',
            'schedule_name',
            'total_papers_fetched',
            'total_papers_passed_screening',
            'tokens_in',
            'tokens_out',
            'tokens_consumed',
            'usd_cost',
        ]


class PipelineRunDetailSerializer(PipelineRunSerializer):
    component_runs = ComponentRunSerializer(many=True, read_only=True)
    storage_stats = serializers.SerializerMethodField()
    papers_count = serializers.SerializerMethodField()
    duplicates_count = serializers.SerializerMethodField()
    extractions_count = serializers.SerializerMethodField()

    class Meta(PipelineRunSerializer.Meta):
        fields = PipelineRunSerializer.Meta.fields + [
            'component_runs',
            'storage_stats',
            'papers_count',
            'duplicates_count',
            'extractions_count',
        ]

    def get_storage_stats(self, obj):
        ws_id = str(obj.workspace_id)
        run_id = str(obj.id)
        run_dir = f"workspaces/{ws_id}/runs/{run_id}"
        try:
            return _get_run_storage_stats(run_dir)
        except Exception:
            return {"total_bytes": 0, "total_files": 0, "size_formatted": "0 B"}

    def get_papers_count(self, obj):
        return obj.paper_metrics.count()

    def get_duplicates_count(self, obj):
        search_runs = [cr for cr in obj.component_runs.all() if cr.step_type == 'search']
        return sum(
            int((cr.metrics or {}).get("duplicates_count", (cr.metrics or {}).get("total_duplicates", (cr.metrics or {}).get("duplicates_skipped", (cr.metrics or {}).get("total_duplicates_skipped", 0)))) or 0)
            for cr in search_runs
        )

    def get_extractions_count(self, obj):
        return Extraction.objects.filter(paper__metrics__pipeline_run=obj).distinct().count()


class TriggerStepSerializer(serializers.Serializer):
    step_type = serializers.ChoiceField(
        choices=[
            ('search', 'Search & Ingestion'),
            ('abstract_screening', 'Abstract Screening'),
            ('download', 'PDF Binary Download'),
            ('ocr', 'Layout OCR Extraction'),
            ('full_text_screening', 'Full-Text Screening'),
            ('screening', 'Abstract & Full-Text Screening (Legacy)'),
            ('extraction', 'Dynamic Parameter Extraction'),
            ('signal_score', 'Signal Score Evaluation'),
            ('reporting', 'Executive Narrative & Notification Dispatch'),
        ],
        required=True,
        help_text="Target pipeline component step to trigger"
    )
    stage = serializers.ChoiceField(
        choices=[
            ('abstract', 'Abstract Screening'),
            ('full_text', 'Multimodal Full-Text Screening'),
        ],
        required=False,
        default='abstract',
        help_text="Screening stage: 'abstract' or 'full_text'"
    )
    limit = serializers.IntegerField(
        required=False,
        default=50,
        min_value=1,
        max_value=500,
        help_text="Maximum number of papers to process in this step"
    )
    skip_abstract_screening = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If True during screening step, screens full-text directly"
    )
    date_range_days = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        help_text="Days range for search step query"
    )
    query_prefix = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional search query modifier"
    )
    notification_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        help_text="Recipient email for step completion notification"
    )


class CreatePipelineRunSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=True, help_text="Target Workspace UUID")
    reprocess_existing = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If True, reprocesses existing workspace papers without scraping new ones"
    )
    name = serializers.CharField(
        required=False,
        default="SLR Review Run",
        max_length=255,
        help_text="Descriptive run name"
    )
