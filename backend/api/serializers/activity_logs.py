from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from research_intelligence.models import UserActivityLog


class UserActivityLogSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    workspace_display = serializers.SerializerMethodField()

    class Meta:
        model = UserActivityLog
        fields = [
            'id',
            'user',
            'workspace',
            'user_username',
            'user_email',
            'workspace_name',
            'interface',
            'action_name',
            'status',
            'input_params',
            'output_summary',
            'error_message',
            'execution_time_ms',
            'api_key_id',
            'ip_address',
            'user_agent',
            'timestamp',
            'user_display',
            'workspace_display'
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_user_display(self, obj) -> str:
        return obj.user_username or (obj.user.username if obj.user else "Anonymous")

    @extend_schema_field(serializers.CharField)
    def get_workspace_display(self, obj) -> str:
        return obj.workspace_name or (obj.workspace.name if obj.workspace else "")
