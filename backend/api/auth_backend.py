from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import User
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class WorkspaceJWTAuthentication(JWTAuthentication):
    """
    Subclasses SimpleJWT's default authentication class to extract
    optional tenant 'workspace_id' claim and resolve the authenticated user
    from the database.

    Rejects tokens that don't contain a valid, active user_id.
    """
    def get_user(self, validated_token):
        # Resolve a real user from the token's user_id claim
        user_id = validated_token.get('user_id')
        if not user_id or user_id == 0:
            raise AuthenticationFailed('Token does not contain a valid user_id.')

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed('User referenced by token no longer exists.')

        if not user.is_active:
            raise AuthenticationFailed('User account is disabled.')

        # Attach optional workspace_id if present in token payload
        workspace_id = validated_token.get('workspace_id')
        user._workspace_id = workspace_id
        return user


class WorkspaceJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """
    OpenAPI authentication schema extension for WorkspaceJWTAuthentication.
    """
    target_class = 'api.auth_backend.WorkspaceJWTAuthentication'
    name = 'jwtAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': 'Enter JWT Bearer token obtained from /api/auth/login/',
        }
