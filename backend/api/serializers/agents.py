from rest_framework import serializers
from research_intelligence.models import ResearchAgentProcess


class StartResearchAgentSerializer(serializers.Serializer):
    workspace = serializers.UUIDField(required=True, help_text="Workspace UUID to launch the agent in")
    name = serializers.CharField(required=False, allow_blank=True, default="Autonomous Literature Review", help_text="Human-readable name for the research process")
    limit = serializers.IntegerField(required=False, default=50, help_text="Max number of candidate papers to fetch & process")
    date_range_days = serializers.IntegerField(required=False, allow_null=True, help_text="Filter query to the last N days")
    query_prefix = serializers.CharField(required=False, allow_blank=True, help_text="Search query prefix override")
    skip_abstract_screening = serializers.BooleanField(required=False, default=False, help_text="Skip abstract screening and screen directly on full text")
    notification_email = serializers.EmailField(required=False, allow_null=True, help_text="Optional email to receive notification upon completion")


class ResearchAgentProcessSerializer(serializers.ModelSerializer):
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    pipeline_run_status = serializers.CharField(source='pipeline_run.status', read_only=True, default=None)

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
            'configuration_override',
            'step_history',
            'error_message',
            'started_at',
            'updated_at',
            'completed_at'
        ]
        read_only_fields = ['id', 'status', 'current_step', 'step_history', 'error_message', 'started_at', 'updated_at', 'completed_at']
