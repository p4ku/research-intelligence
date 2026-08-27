from rest_framework import serializers
from research_intelligence.models import PaperChatSession, PaperChatMessage, Paper


from drf_spectacular.utils import extend_schema_field


class PaperChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperChatMessage
        fields = [
            'id',
            'session',
            'sender',
            'status',
            'deep_thinking',
            'llm_model',
            'question',
            'message',
            'citations',
            'visual_citations',
            'hallucination_guard',
            'celery_task_id',
            'tokens_in',
            'tokens_out',
            'total_tokens',
            'usd_cost',
            'error_message',
            'created_at',
            'completed_at',
        ]
        read_only_fields = fields


class PaperChatSessionSerializer(serializers.ModelSerializer):
    paper_title = serializers.CharField(source='paper.title', read_only=True)
    paper_doi = serializers.CharField(source='paper.doi', read_only=True, default=None)
    messages_count = serializers.SerializerMethodField()

    class Meta:
        model = PaperChatSession
        fields = [
            'id',
            'workspace',
            'paper',
            'paper_title',
            'paper_doi',
            'user',
            'title',
            'summary',
            'messages_count',
            'total_tokens_in',
            'total_tokens_out',
            'total_tokens',
            'total_usd_cost',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField)
    def get_messages_count(self, obj):
        return obj.messages.count()


class PaperChatSessionDetailSerializer(PaperChatSessionSerializer):
    messages = PaperChatMessageSerializer(many=True, read_only=True)

    class Meta(PaperChatSessionSerializer.Meta):
        fields = PaperChatSessionSerializer.Meta.fields + ['messages']


class PaperChatSubmitSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True, help_text="Workspace UUID (optional if paper belongs to uniquely identifiable workspace)")
    paper_id = serializers.UUIDField(required=False, allow_null=True, help_text="Target Paper UUID (optional for workspace-level corpus chat)")
    question = serializers.CharField(required=True, min_length=2, help_text="Research question or query for the paper")
    session_id = serializers.UUIDField(required=False, allow_null=True, help_text="Existing chat session UUID to continue conversation")
    deep_thinking = serializers.BooleanField(required=False, default=False, help_text="If True, enables Gemini 3.7 Flash deep scientific reasoning mode")
    sync = serializers.BooleanField(required=False, default=False, help_text="If True, executes synchronously and returns answer immediately. Default False returns 202 Accepted async task.")


class PaperChatAsyncResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="Task status ('pending', 'processing', 'completed', 'failed')")
    message_id = serializers.UUIDField(help_text="Created message UUID")
    session_id = serializers.UUIDField(help_text="Chat session UUID")
    task_id = serializers.CharField(help_text="Celery background task ID", allow_blank=True, default="")
    poll_url = serializers.CharField(help_text="Polling endpoint to check status and receive response")
