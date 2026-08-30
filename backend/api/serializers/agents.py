from rest_framework import serializers
from research_intelligence.models import ResearchAgentProcess


class StartResearchAgentSerializer(serializers.Serializer):
    workspace = serializers.UUIDField(required=True, help_text="Workspace UUID to launch the agent in")
    name = serializers.CharField(required=False, allow_blank=True, default="Autonomous Literature Review", help_text="Human-readable name for the research process")
    limit = serializers.IntegerField(required=False, default=50, help_text="Max number of candidate papers to fetch & process")
    date_range_days = serializers.IntegerField(required=False, allow_null=True, help_text="Filter query to the last N days")
    query_prefix = serializers.CharField(required=False, allow_blank=True, help_text="Search query prefix override")
    skip_abstract_screening = serializers.BooleanField(required=False, default=False, help_text="Skip abstract screening and screen directly on full text")
    reprocess_existing = serializers.BooleanField(required=False, default=False, help_text="Reprocess existing workspace papers without re-scraping")
    notification_email = serializers.EmailField(required=False, allow_null=True, help_text="Optional email to receive notification upon completion")


class ResearchAgentProcessSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    pipeline_run_status = serializers.CharField(source='pipeline_run.status', read_only=True, default=None)
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
