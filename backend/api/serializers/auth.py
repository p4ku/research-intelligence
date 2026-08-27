from rest_framework import serializers
from django.contrib.auth.models import User


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'is_superuser', 'is_staff']

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username


class LoginSerializer(serializers.Serializer):
    # Username / Email + Password credentials
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    username_or_email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    # Legacy / FastMCP API Key credentials
    api_key = serializers.CharField(required=False, allow_blank=True)
    workspace_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, data):
        # 1. API key auth
        if data.get('api_key'):
            return data

        # 2. Email / Username + Password auth
        password = data.get('password')
        identifier = data.get('username_or_email') or data.get('username') or data.get('email')

        if not identifier or not password:
            raise serializers.ValidationError(
                "Either (username/email and password) or (api_key) must be provided."
            )

        data['identifier'] = identifier.strip()
        return data
