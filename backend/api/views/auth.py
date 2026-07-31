from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken
from ..serializers.auth import LoginSerializer
from research_intelligence.models import APIKey


class LoginView(APIView):
    """
    Authenticates via MCP API key and returns JWT tokens with the real user_id.
    The api_key must be in format 'key_id:secret' and must match an active APIKey.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            api_key_raw = serializer.validated_data['api_key']
            workspace_id = serializer.validated_data['workspace_id']

            # Validate API key against APIKey model
            # Expected format: "key_id:secret" or just "secret" for legacy compat
            parts = api_key_raw.split(':', 1)
            if len(parts) == 2:
                key_id, secret = parts
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        key_id=key_id, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response(
                        {"error": "Invalid API key."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
                if not api_key_obj.check_secret(secret):
                    return Response(
                        {"error": "Invalid API key secret."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
            else:
                # Legacy: try to find by matching hashed secret across all active keys
                import hashlib
                hashed = hashlib.sha256(api_key_raw.encode()).hexdigest()
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        hashed_secret=hashed, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response(
                        {"error": "Invalid API key."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )

            user = api_key_obj.user
            api_key_obj.update_last_used()

            # Generate token with real user_id
            refresh = RefreshToken.for_user(user)
            refresh['workspace_id'] = str(workspace_id)

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "workspace_id": workspace_id,
                    "user_id": user.id,
                    "username": user.username
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WorkspaceTokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)
    access = serializers.CharField(read_only=True)

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs['refresh'])
            data = {'access': str(refresh.access_token)}
            return data
        except Exception as e:
            raise InvalidToken(str(e))

class TokenRefreshView(APIView):
    """
    Regenerates a fresh access token given a valid SimpleJWT refresh token,
    without executing database user queries.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = WorkspaceTokenRefreshSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
