from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken
from ..serializers.auth import LoginSerializer

class LoginView(APIView):
    """
    Handles authentication and returns workspace context credentials using SimpleJWT.
    Generates tokens directly without database User model instantiation.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            workspace_id = serializer.validated_data['workspace_id']

            # Generate RefreshToken directly (bypasses django User model creation)
            refresh = RefreshToken()
            refresh['workspace_id'] = str(workspace_id)
            refresh['user_id'] = 0  # Default non-null dummy user ID claim required by SimpleJWT

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "workspace_id": workspace_id
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
