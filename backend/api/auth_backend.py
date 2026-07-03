from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import User

class WorkspaceJWTAuthentication(JWTAuthentication):
    """
    Subclasses SimpleJWT's default authentication class to extract
    the tenant 'workspace_id' claim and authenticate the request
    context without performing standard Django user database lookups.
    """
    def get_user(self, validated_token):
        workspace_id = validated_token.get('workspace_id')
        if not workspace_id:
            raise AuthenticationFailed('Token payload missing workspace context.')

        # Return a mock active user instance with a workspace-linked username
        user = User(username=f'workspace_{str(workspace_id)[:8]}', is_active=True)
        return user
