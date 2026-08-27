from rest_framework import serializers
from chat.models import PaperChatMessage


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
