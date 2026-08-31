import os
import hashlib
from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from research_intelligence.models import APIKey


def verify_metrics_credentials(request) -> bool:
    """
    Validates credentials for Prometheus scraping endpoint (/metrics).
    Accepts:
    1. Dedicated Prometheus scraper bearer token or header (METRICS_EXPORT_KEY).
    2. FastMCP / System APIKey (Header 'X-API-Key' or 'Authorization: Api-Key key_id:secret').
    3. Standard authenticated Django User / JWT session.
    """
    # 1. Standard Django / JWT User session
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        return True

    auth_header = request.META.get('HTTP_AUTHORIZATION', '').strip()
    x_metrics_key = request.META.get('HTTP_X_METRICS_KEY', '').strip()
    x_api_key = request.META.get('HTTP_X_API_KEY', '').strip()

    # 2. Check dedicated Prometheus scrape token
    configured_metrics_key = getattr(settings, 'METRICS_EXPORT_KEY', '') or os.environ.get('METRICS_EXPORT_KEY', '')
    if configured_metrics_key:
        if x_metrics_key and x_metrics_key == configured_metrics_key:
            return True
        if auth_header.startswith('Bearer '):
            token_val = auth_header[7:].strip()
            if token_val == configured_metrics_key:
                return True

    # 3. Check FastMCP / System API Key
    candidate_api_key = x_api_key or (auth_header[8:].strip() if auth_header.startswith('Api-Key ') else '')
    if candidate_api_key:
        parts = candidate_api_key.split(':', 1)
        if len(parts) == 2:
            key_id, secret = parts
            api_key_obj = APIKey.objects.filter(key_id=key_id, is_active=True).first()
            if api_key_obj and api_key_obj.check_secret(secret):
                return True
        else:
            hashed = hashlib.sha256(candidate_api_key.encode()).hexdigest()
            if APIKey.objects.filter(hashed_secret=hashed, is_active=True).exists():
                return True

    return False
