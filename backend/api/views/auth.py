import hashlib
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken

from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..serializers.auth import LoginSerializer, UserProfileSerializer
from research_intelligence.models import APIKey, WorkspaceMember


class LoginView(APIView):
    """
    Authenticates via:
    1. Email or Username + Password (standard Django credentials).
    2. FastMCP / Agent API key (in format 'key_id:secret' or secret).
    Returns JWT access & refresh tokens along with user profile metadata.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Successful authentication returning access & refresh tokens"),
            400: OpenApiResponse(description="Invalid request payload"),
            401: OpenApiResponse(description="Invalid credentials or inactive user account"),
        },
        tags=['Authentication']
    )
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data

        # --- 1. FastMCP API Key Authentication ---
        if validated_data.get('api_key'):
            api_key_raw = validated_data['api_key']
            workspace_id = validated_data.get('workspace_id')

            parts = api_key_raw.split(':', 1)
            if len(parts) == 2:
                key_id, secret = parts
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        key_id=key_id, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response({"error": "Invalid API key."}, status=status.HTTP_401_UNAUTHORIZED)

                if not api_key_obj.check_secret(secret):
                    return Response({"error": "Invalid API key secret."}, status=status.HTTP_401_UNAUTHORIZED)
            else:
                hashed = hashlib.sha256(api_key_raw.encode()).hexdigest()
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        hashed_secret=hashed, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response({"error": "Invalid API key."}, status=status.HTTP_401_UNAUTHORIZED)

            user = api_key_obj.user
            api_key_obj.update_last_used()

            refresh = RefreshToken.for_user(user)
            if workspace_id:
                refresh['workspace_id'] = str(workspace_id)

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "workspace_id": str(workspace_id) if workspace_id else None,
                    "user_id": user.id,
                    "username": user.username,
                    "user": UserProfileSerializer(user).data,
                },
                status=status.HTTP_200_OK
            )

        # --- 2. Username / Email + Password Authentication ---
        identifier = validated_data.get('identifier')
        password = validated_data.get('password')
        workspace_id = validated_data.get('workspace_id')

        # Try authenticating directly with username
        user = authenticate(request, username=identifier, password=password)

        # If direct username auth failed, lookup user by email
        if user is None:
            user_by_email = User.objects.filter(email__iexact=identifier).first()
            if user_by_email:
                user = authenticate(request, username=user_by_email.username, password=password)

        if user is None:
            return Response(
                {"error": "Invalid email/username or password."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {"error": "User account is disabled."},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        if workspace_id:
            refresh['workspace_id'] = str(workspace_id)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "workspace_id": str(workspace_id) if workspace_id else None,
                "user_id": user.id,
                "username": user.username,
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK
        )



class UserProfileView(APIView):
    """
    Returns the authenticated user's profile and workspace membership summary.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: UserProfileSerializer,
            401: OpenApiResponse(description="Unauthorized - Token missing or expired"),
        },
        tags=['Authentication']
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        profile_data = UserProfileSerializer(user).data
        
        # Summary of accessible workspaces
        memberships = WorkspaceMember.objects.filter(user=user).select_related('workspace')
        profile_data['workspaces_count'] = memberships.count() if not user.is_superuser else None
        return Response(profile_data, status=status.HTTP_200_OK)


class WorkspaceTokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True, help_text="Valid SimpleJWT refresh token")
    access = serializers.CharField(read_only=True, help_text="New access JWT token")

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs['refresh'])
            data = {'access': str(refresh.access_token)}
            return data
        except Exception as e:
            raise InvalidToken(str(e))


class TokenRefreshView(APIView):
    """
    Regenerates a fresh access token given a valid SimpleJWT refresh token.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        request=WorkspaceTokenRefreshSerializer,
        responses={
            200: WorkspaceTokenRefreshSerializer,
            401: OpenApiResponse(description="Invalid or expired refresh token"),
        },
        tags=['Authentication']
    )
    def post(self, request, *args, **kwargs):
        serializer = WorkspaceTokenRefreshSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
