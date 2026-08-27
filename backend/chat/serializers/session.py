from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from chat.models import PaperChatSession
from .message import PaperChatMessageSerializer


class PaperChatSessionSerializer(serializers.ModelSerializer):
    paper_title = serializers.CharField(source='paper.title', read_only=True, default=None, allow_null=True)
    paper_doi = serializers.CharField(source='paper.doi', read_only=True, default=None, allow_null=True)
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
