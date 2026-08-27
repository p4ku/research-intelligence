from rest_framework import serializers


class PaperChatSubmitSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True, help_text="Workspace UUID containing the paper")
    paper_id = serializers.UUIDField(required=False, allow_null=True, help_text="Paper UUID to ask questions about")
    session_id = serializers.UUIDField(required=False, allow_null=True, help_text="Optional existing chat session UUID")
    question = serializers.CharField(required=True, help_text="User question or research prompt")
    sync = serializers.BooleanField(required=False, default=False, help_text="If True, executes synchronously instead of queueing to Celery")
    deep_thinking = serializers.BooleanField(required=False, default=False, help_text="If True, triggers multi-step scratchpad reasoning and chain-of-thought analysis")


class PaperChatAsyncResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message_id = serializers.UUIDField()
    session_id = serializers.UUIDField()
    task_id = serializers.CharField(required=False, allow_blank=True)
    paper_id = serializers.UUIDField()
    question = serializers.CharField()
    deep_thinking = serializers.BooleanField(default=False)
    created_at = serializers.DateTimeField()
