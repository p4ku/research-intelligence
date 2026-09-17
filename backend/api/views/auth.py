from django.conf import settings
import hashlib
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken

from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..serializers.auth import (
    LoginSerializer,
    UserProfileSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
    LogoutSerializer,
)
from ..throttles import LoginRateThrottle
from research_intelligence.models import APIKey, WorkspaceMember


class LoginView(APIView):
    """
    Authenticates via:
    1. Email or Username + Password (standard Django credentials).
    2. FastMCP / Agent API key (in format 'key_id:secret' or secret).
    Returns JWT access & refresh tokens along with user profile metadata.
    Throttled at 5 requests/minute to prevent brute-force attacks.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

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
    Retrieves or updates the authenticated user's profile metadata (username, email, first_name, last_name).
    Users can only view and edit their own account profile.
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
        profile_data['workspaces_count'] = WorkspaceMember.objects.filter(user=user).count()
        return Response(profile_data, status=status.HTTP_200_OK)

    @extend_schema(
        request=UpdateProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiResponse(description="Validation error (e.g. username/email already taken)"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=['Authentication']
    )
    def patch(self, request, *args, **kwargs):
        serializer = UpdateProfileSerializer(data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        validated = serializer.validated_data

        if 'username' in validated:
            user.username = validated['username']
        if 'email' in validated:
            user.email = validated['email']
        if 'first_name' in validated:
            user.first_name = validated['first_name']
        if 'last_name' in validated:
            user.last_name = validated['last_name']

        user.save()
        return Response(UserProfileSerializer(user).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=UpdateProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=['Authentication']
    )
    def put(self, request, *args, **kwargs):
        return self.patch(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """
    Allows the authenticated user to change their account password.
    Requires providing and verifying the current old password.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Invalid old password or mismatched confirmation"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=['Authentication']
    )
    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        old_password = serializer.validated_data['old_password']
        new_password = serializer.validated_data['new_password']

        if not user.check_password(old_password):
            return Response(
                {"old_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        # Revoke/Blacklist all outstanding refresh tokens for this user
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            outstanding = OutstandingToken.objects.filter(user=user)
            for ot in outstanding:
                BlacklistedToken.objects.get_or_create(token=ot)
        except Exception:
            pass

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    """
    Invalidates/blacklists the provided refresh token, effectively logging out the session.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        responses={
            200: OpenApiResponse(description="Logged out successfully"),
            400: OpenApiResponse(description="Invalid or missing refresh token"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=['Authentication']
    )
    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh_token = serializer.validated_data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class WorkspaceTokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True, help_text="Valid SimpleJWT refresh token")
    access = serializers.CharField(read_only=True, help_text="New access JWT token")

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs['refresh'])
            data = {'access': str(refresh.access_token)}
            if getattr(settings, 'SIMPLE_JWT', {}).get('ROTATE_REFRESH_TOKENS', False):
                if getattr(settings, 'SIMPLE_JWT', {}).get('BLACKLIST_AFTER_ROTATION', False):
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        pass
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                data['refresh'] = str(refresh)
            return data
        except Exception as e:
            raise serializers.ValidationError({"refresh": str(e)})


class TokenRefreshView(APIView):
    """
    Regenerates a fresh access token given a valid SimpleJWT refresh token.
    Supports token rotation and blacklist validation.
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


class CreateUserView(APIView):
    """
    Create a new Django user account with an encrypted password.
    Requires staff member or superuser privileges.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create User Account",
        description="Creates a new user account with credentials and role flags (staff/superuser only).",
        tags=['Authentication'],
        responses={201: OpenApiResponse(description="User created successfully")}
    )
    def post(self, request, *args, **kwargs):
        import json
        from mcp_server.tools.users.management import create_user_logic
        data = request.data
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        is_staff = data.get("is_staff", False)
        is_superuser = data.get("is_superuser", False)

        res_json = create_user_logic(
            user=request.user,
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        res_data = json.loads(res_json)
        if res_data.get("status") == "error":
            err_msg = res_data.get("error", "")
            if "permission" in err_msg.lower() or "denied" in err_msg.lower():
                return Response(res_data, status=status.HTTP_403_FORBIDDEN)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
        return Response(res_data, status=status.HTTP_201_CREATED)


class DeleteUserView(APIView):
    """
    Delete a Django user account by username.
    Requires staff member or superuser privileges.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete User Account",
        description="Deletes a user account by username (staff/superuser only).",
        tags=['Authentication'],
        responses={200: OpenApiResponse(description="User deleted successfully")}
    )
    def delete(self, request, username, *args, **kwargs):
        import json
        from mcp_server.tools.users.management import delete_user_logic
        res_json = delete_user_logic(user=request.user, user_id_or_username=username)
        res_data = json.loads(res_json)
        if res_data.get("status") == "error":
            err_msg = res_data.get("error", "")
            if "permission" in err_msg.lower() or "denied" in err_msg.lower():
                return Response(res_data, status=status.HTTP_403_FORBIDDEN)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)
        return Response(res_data, status=status.HTTP_200_OK)
