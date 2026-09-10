from rest_framework import serializers
from research_intelligence.models import ResearchAgentProcess
from .pipeline_runs import validate_iso_date


class StartResearchAgentSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=False, help_text="Target Workspace UUID to launch the agent in")
    workspace = serializers.UUIDField(required=False, help_text="Target Workspace UUID alias")
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="Autonomous Literature Review", help_text="Human-readable name for the research process")
    limit = serializers.IntegerField(required=False, default=2000, min_value=1, max_value=10000, help_text="Max number of candidate papers to fetch & process (default: 2000, max: 10000)")
    start_date = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None, help_text="ISO start date (e.g. '2026-08-01')")
    end_date = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None, help_text="ISO end date (e.g. '2026-08-31')")
    n_last_days = serializers.IntegerField(required=False, default=None, allow_null=True, min_value=1, max_value=3650, help_text="Lookback window in days (default: 7)")
    query_prefix = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="", help_text="Search query prefix override")
    skip_abstract_screening = serializers.BooleanField(required=False, default=False, help_text="Skip abstract screening and screen directly on full text")
    reprocess_existing = serializers.BooleanField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Reprocess existing workspace papers without re-scraping. If omitted/null, falls back to workspace.reprocess_existing."
    )
    notification_email = serializers.EmailField(required=False, allow_null=True, allow_blank=True, default=None, help_text="Optional email to receive notification upon completion")

    def validate(self, attrs):
        ws_id = attrs.get("workspace_id") or attrs.get("workspace")
        if not ws_id:
            raise serializers.ValidationError({"workspace_id": ["This field is required."]})
        attrs["workspace_id"] = ws_id
        if attrs.get("query_prefix") is None:
            attrs["query_prefix"] = ""
        if not attrs.get("name"):
            attrs["name"] = "Autonomous Literature Review"
        return attrs

    def validate_start_date(self, value):
        return validate_iso_date(value, "start_date")

    def validate_end_date(self, value):
        return validate_iso_date(value, "end_date")



class ResearchAgentProcessSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    pipeline_run = serializers.UUIDField(source='id', read_only=True)
    pipeline_run_status = serializers.CharField(source='status', read_only=True, default=None)
    current_step = serializers.CharField(source='current_stage', read_only=True)
    stopped_at_step = serializers.CharField(source='stopped_at_stage', read_only=True, allow_null=True)
    stop_reason = serializers.CharField(source='status_message', read_only=True)
    error_message = serializers.CharField(source='status_message', read_only=True, allow_null=True)
    duration_seconds = serializers.FloatField(read_only=True)
    execution_time_display = serializers.CharField(read_only=True)

    class Meta:
        model = ResearchAgentProcess
        fields = [
            'id',
            'workspace',
            'workspace_name',
            'pipeline_run',
            'pipeline_run_status',
            'name',
            'status',
            'current_step',
            'stopped_at_step',
            'stop_reason',
            'stage_results',
            'configuration_override',
            'step_history',
            'error_message',
            'duration_seconds',
            'execution_time_display',
            'started_at',
            'updated_at',
            'completed_at'
        ]
        read_only_fields = [
            'id', 'status', 'current_step', 'stopped_at_step', 'stop_reason', 'stage_results',
            'step_history', 'error_message', 'duration_seconds', 'execution_time_display',
            'started_at', 'updated_at', 'completed_at'
        ]
