"""
Periodic Token Cleanup & Blacklist Pruning.

Periodically cleans up expired JWT tokens and blacklisted tokens from the database
to prevent table bloat and optimize query performance.
Tokens whose expires_at timestamp is in the past are automatically purged since expired tokens
are cryptographically rejected before blacklist lookup.
"""

import logging
from typing import Dict, Any
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def cleanup_expired_blacklisted_tokens() -> Dict[str, Any]:
    """
    Purges expired OutstandingToken and BlacklistedToken records from the database.
    """
    close_old_connections()
    now = timezone.now()
    deleted_outstanding = 0
    deleted_blacklisted = 0

    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

        # 1. Delete blacklisted tokens linked to already expired outstanding tokens
        expired_blacklisted = BlacklistedToken.objects.filter(token__expires_at__lt=now)
        deleted_blacklisted = expired_blacklisted.count()
        expired_blacklisted.delete()

        # 2. Delete outstanding tokens whose expires_at is in the past
        expired_outstanding = OutstandingToken.objects.filter(expires_at__lt=now)
        deleted_outstanding = expired_outstanding.count()
        expired_outstanding.delete()

        if deleted_blacklisted > 0 or deleted_outstanding > 0:
            logger.info(
                f"🧹 [TOKEN CLEANUP] Pruned {deleted_blacklisted} expired BlacklistedTokens "
                f"and {deleted_outstanding} expired OutstandingTokens (Cutoff: {now.isoformat()})."
            )
        return {
            "success": True,
            "deleted_blacklisted": deleted_blacklisted,
            "deleted_outstanding": deleted_outstanding,
            "timestamp": now.isoformat(),
        }
    except Exception as e:
        logger.warning(f"Error during expired token cleanup: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": now.isoformat(),
        }


@shared_task
def cleanup_expired_tokens_task() -> Dict[str, Any]:
    """Celery periodic task invoked by Celery Beat to flush expired blacklisted JWTs."""
    return cleanup_expired_blacklisted_tokens()
