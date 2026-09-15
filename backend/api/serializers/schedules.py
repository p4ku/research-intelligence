from rest_framework import serializers
from research_intelligence.models import WorkflowSchedule


class WorkflowScheduleSerializer(serializers.ModelSerializer):
    workspace_name = serializers.ReadOnlyField(source='workspace.name')
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    schedule_description = serializers.CharField(read_only=True)
    cron_expression = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    last_status = serializers.CharField(source='current_execution_status', read_only=True)
    successful_runs_count = serializers.IntegerField(read_only=True)
    failed_runs_count = serializers.IntegerField(read_only=True)
    success_rate_percent = serializers.FloatField(read_only=True)

    def validate_cron_expression(self, value):
        return value or ''

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        test_instance = WorkflowSchedule()
        if self.instance:
            for field in self.instance._meta.fields:
                setattr(test_instance, field.name, getattr(self.instance, field.name))
        for k, v in attrs.items():
            setattr(test_instance, k, v)
        try:
            test_instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, 'message_dict') else e.messages)
        return attrs

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
            'n_last_days',
            'reprocess_existing',
            'prevent_overlap',
            'configuration_override',
            'last_run_at',
            'next_run_at',
            'last_pipeline_run',
            'last_status',
            'total_runs_count',
            'successful_runs_count',
            'failed_runs_count',
            'consecutive_failures_count',
            'max_consecutive_failures',
            'success_rate_percent',
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
            'successful_runs_count',
            'failed_runs_count',
            'consecutive_failures_count',
            'success_rate_percent',
            'created_by',
            'created_at',
            'updated_at',
        ]

    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)
