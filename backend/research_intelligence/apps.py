import sys
import hashlib
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_create_default_superuser(sender, **kwargs):
    """
    Signal handler connected to post_migrate to auto-create default superuser
    'admin' with password 'schwarz123!' when database is empty.
    """
    try:
        from django.contrib.auth import get_user_model
        from research_intelligence.models import APIKey
        User = get_user_model()

        if not User.objects.exists():
            admin_user = User.objects.create_superuser(
                username="admin",
                email="admin@schwarz-digits.cloud",
                password="schwarz123!"
            )
            print("Auto-created default superuser 'admin' (Password: schwarz123!)", file=sys.stderr)

            # Auto-create default MCP API key for admin
            hashed_secret = hashlib.sha256("schwarz123!".encode()).hexdigest()
            APIKey.objects.get_or_create(
                key_id="admin_mcp_key",
                defaults={
                    "name": "Default Admin MCP Key",
                    "user": admin_user,
                    "hashed_secret": hashed_secret,
                    "scopes": ["*"],
                    "is_active": True
                }
            )
            print("Auto-created default MCP API Key (key_id: admin_mcp_key, secret: schwarz123!)", file=sys.stderr)
    except Exception:
        pass


class ResearchIntelligenceConfig(AppConfig):
    name = 'research_intelligence'

    def ready(self):
        post_migrate.connect(auto_create_default_superuser, sender=self)
