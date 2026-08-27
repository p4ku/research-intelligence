from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'is_superuser', 'is_staff']

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username


class UpdateProfileSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, min_length=3, max_length=150, help_text="New unique username")
    email = serializers.EmailField(required=False, help_text="New unique email address")
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_username(self, value):
        user = self.context.get('request').user if self.context.get('request') else None
        if User.objects.filter(username__iexact=value.strip()).exclude(pk=user.pk if user else None).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value.strip()

    def validate_email(self, value):
        user = self.context.get('request').user if self.context.get('request') else None
        if User.objects.filter(email__iexact=value.strip()).exclude(pk=user.pk if user else None).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value.strip().lower()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True, help_text="Current password for verification")
    new_password = serializers.CharField(required=True, write_only=True, min_length=8, help_text="New password (minimum 8 characters)")
    confirm_password = serializers.CharField(required=True, write_only=True, help_text="Confirm new password")

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({"new_password": "New password must be different from old password."})
        return attrs


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
