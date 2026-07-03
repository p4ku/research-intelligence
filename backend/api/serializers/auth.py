from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    api_key = serializers.CharField(required=True)
    workspace_id = serializers.UUIDField(required=True)
