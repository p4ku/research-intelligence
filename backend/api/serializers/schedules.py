from rest_framework import serializers
from research_intelligence.models import WorkflowSchedule


class WorkflowScheduleSerializer(serializers.ModelSerializer):
    workspace_name = serializers.ReadOnlyField(source='workspace.name')
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    schedule_description = serializers.CharField(read_only=True)

    class Meta:
        model = WorkflowSchedule
        fields = [
            'id',
            'workspace',
            'workspace_name',
            'name',
            'is_active',
            'frequency',
            'frequency_display',
            'one_off_datetime',
            'time_of_day',
            'days_of_week',
            'day_of_month',
            'interval_hours',
            'cron_expression',
            'timezone_name',
            'schedule_description',
            'reprocess_existing',
            'configuration_override',
            'last_run_at',
            'next_run_at',
            'last_pipeline_run',
            'last_status',
            'total_runs_count',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'workspace_name',
            'frequency_display',
            'schedule_description',
            'last_run_at',
            'next_run_at',
            'last_pipeline_run',
            'last_status',
            'total_runs_count',
            'created_by',
            'created_at',
            'updated_at',
        ]

    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)
