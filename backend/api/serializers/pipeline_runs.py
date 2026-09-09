from datetime import datetime
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
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
    period = serializers.SerializerMethodField()
    total_papers_screened = serializers.IntegerField(source='total_papers_fetched', read_only=True)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_period(self, obj):
        return getattr(obj, 'period', None)

    class Meta:
        model = PipelineRun
        fields = [
            'id',
            'name',
            'workspace',
            'workspace_name',
            'schedule',
            'schedule_name',
            'run_date',
            'status',
            'current_stage',
            'stopped_at_stage',
            'configuration_override',
            'period',
            'total_papers_fetched',
            'total_papers_screened',
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
            'period',
            'run_date',
            'started_at',
            'completed_at',
            'duration_seconds',
            'execution_time_display',
            'workspace_name',
            'triggered_by_username',
            'schedule_name',
            'total_papers_fetched',
            'total_papers_screened',
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
            'stage_results',
            'step_history',
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
            int((cr.metrics or {}).get("duplicates_count", 0))
            for cr in search_runs
        )

    def get_extractions_count(self, obj):
        return Extraction.objects.filter(paper_id__in=obj.paper_metrics.values('paper_id')).count()


def validate_iso_date(value: str, field_name: str) -> str:
    if not value:
        return value
    clean = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%d", "%Y/%m/%d"):
        try:
            datetime.strptime(clean, fmt)
            return clean
        except ValueError:
            continue
    try:
        datetime.fromisoformat(clean)
        return clean
    except Exception:
        raise serializers.ValidationError(
            f"Invalid date format for {field_name}: '{value}'. Expected ISO-8601 string (e.g. '2026-09-01')."
        )


class TriggerStepSerializer(serializers.Serializer):
    step_type = serializers.ChoiceField(
        choices=[
            ('search', 'Academic Search & Ingestion'),
            ('screening', 'Dual-Stage LLM Screening (Abstract or Full-Text)'),
            ('abstract_screening', 'Abstract Screening'),
            ('full_text_screening', 'Multimodal Full-Text Screening'),
            ('download', 'PDF Paper Downloader'),
            ('ocr', 'Document Layout OCR Analysis'),
            ('extraction', 'Dynamic Structured Parameter Extraction'),
            ('signal_score', 'Python Composite Signal Scoring'),
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
    query_prefix = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default="",
        help_text="Optional search query modifier"
    )
    notification_email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="Recipient email for step completion notification"
    )
    start_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="Start date for search query (e.g. '2026-09-01' or '2026-09-01T00:00:00Z')"
    )
    end_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="End date for search query (e.g. '2026-09-06' or '2026-09-06T23:59:59Z')"
    )
    n_last_days = serializers.IntegerField(
        required=False,
        default=None,
        allow_null=True,
        min_value=1,
        max_value=3650,
        help_text="Default number of past days if dates are omitted (default: 7)"
    )

    def validate_start_date(self, value):
        return validate_iso_date(value, "start_date")

    def validate_end_date(self, value):
        return validate_iso_date(value, "end_date")


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
    start_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="Start date for search query"
    )
    end_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="End date for search query"
    )
    n_last_days = serializers.IntegerField(
        required=False,
        default=None,
        allow_null=True,
        min_value=1,
        max_value=3650,
        help_text="Default number of past days if dates are omitted (default: 7)"
    )

    def validate_start_date(self, value):
        return validate_iso_date(value, "start_date")

    def validate_end_date(self, value):
        return validate_iso_date(value, "end_date")


class StartPipelineRunSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=True, help_text="Target Workspace UUID")
    name = serializers.CharField(
        required=False,
        default=None,
        allow_null=True,
        allow_blank=True,
        max_length=255,
        help_text="Descriptive run name"
    )
    start_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="ISO start date (e.g. '2026-09-01' or '2026-09-01T00:00:00Z') for scrapers"
    )
    end_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="ISO end date (e.g. '2026-09-06' or '2026-09-06T23:59:59Z') for scrapers"
    )
    n_last_days = serializers.IntegerField(
        required=False,
        default=None,
        allow_null=True,
        min_value=1,
        max_value=3650,
        help_text="Default number of past days to query if start_date is not specified (default: 7)"
    )
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=1000,
        default=None,
        allow_null=True,
        help_text="Maximum number of papers to fetch/process"
    )
    reprocess_existing = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If True, reprocess existing workspace papers"
    )
    autonomous = serializers.BooleanField(
        required=False,
        default=True,
        help_text="If True, automatically cascades through pipeline stages"
    )
    skip_abstract_screening = serializers.BooleanField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Skip abstract screening and screen full text directly"
    )
    notification_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default=None,
        allow_null=True,
        help_text="Recipient email for completion notification"
    )
    query_prefix = serializers.CharField(
        required=False,
        allow_blank=True,
        default=None,
        allow_null=True,
        help_text="Optional search query modifier"
    )

    def validate_start_date(self, value):
        return validate_iso_date(value, "start_date")

    def validate_end_date(self, value):
        return validate_iso_date(value, "end_date")

