from rest_framework import serializers
from chat.models import PaperChatMessage


class PaperChatMessageSerializer(serializers.ModelSerializer):
    paper_id = serializers.UUIDField(source='session.paper_id', read_only=True, allow_null=True)
    paper_title = serializers.CharField(source='session.paper.title', read_only=True, allow_null=True, default=None)

    class Meta:
        model = PaperChatMessage
        fields = [
            'id',
            'session',
            'paper_id',
            'paper_title',
            'sender',
            'status',
            'deep_thinking',
            'thinking_process',
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
