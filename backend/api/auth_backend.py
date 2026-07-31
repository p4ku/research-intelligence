from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import User


class WorkspaceJWTAuthentication(JWTAuthentication):
    """
    Subclasses SimpleJWT's default authentication class to extract
    the tenant 'workspace_id' claim and resolve the authenticated user
    from the database.

    Rejects tokens that don't contain a valid, saved user_id.
    """
    def get_user(self, validated_token):
        workspace_id = validated_token.get('workspace_id')
        if not workspace_id:
            raise AuthenticationFailed('Token payload missing workspace context.')

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

        user._workspace_id = workspace_id
        return user
