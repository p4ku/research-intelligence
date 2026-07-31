from rest_framework import serializers
from research_intelligence.models import ResearchAgentProcess

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
