import json
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from research_intelligence.models import UserActivityLog

logger = logging.getLogger(__name__)


class UserActionAuditMiddleware(MiddlewareMixin):
    """
    Middleware intercepting REST API requests (/api/) and recording UserActivityLog entries.
    Captures non-safe HTTP methods (POST, PUT, PATCH, DELETE) and key GET endpoints with execution time,
    client IP, user agent, input payload, and status code.
    """

    def process_request(self, request):
        request._audit_t0 = time.time()
        try:
            request._cached_body = request.body
        except Exception:
            request._cached_body = b""

    def process_response(self, request, response):
        path = request.path
        # Only log DRF API endpoints
        if not path.startswith('/api/'):
            return response

        # Ignore static assets or docs if any
        if path.startswith('/api/schema/') or path.startswith('/api/docs/'):
            return response

        t0 = getattr(request, '_audit_t0', time.time())
        execution_time_ms = round((time.time() - t0) * 1000, 2)

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            user = getattr(request, '_user', None)
            if user and not getattr(user, 'is_authenticated', False):
                user = None

        method = request.method
        status_code = response.status_code

        # Determine status string
        if 200 <= status_code < 400:
            status_str = "success"
        elif status_code in (401, 403):
            status_str = "unauthorized"
        else:
            status_str = "failed"

        # Capture input parameters / body
        input_params = None
        if method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            try:
                body = getattr(request, '_cached_body', getattr(request, 'body', b""))
                if body:
                    input_params = json.loads(body.decode('utf-8'))
                elif request.POST:
                    input_params = dict(request.POST)
            except Exception:
                if request.POST:
                    input_params = dict(request.POST)

        # Extract client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        action_name = f"{method} {path}"

        # Capture response summary if brief
        output_summary = {"status_code": status_code}
        try:
            if hasattr(response, 'content') and response.content and len(response.content) < 4000:
                res_data = json.loads(response.content.decode('utf-8'))
                if isinstance(res_data, dict):
                    output_summary.update(res_data)
        except Exception:
            pass

        error_msg = None
        if status_str != "success":
            try:
                if hasattr(response, 'content') and response.content:
                    err_data = json.loads(response.content.decode('utf-8'))
                    error_msg = json.dumps(err_data)
            except Exception:
                error_msg = f"HTTP {status_code}"

        try:
            UserActivityLog.log_action(
                user=user,
                workspace=None, # Automatically resolved by log_action from action_name, input_params, or output_summary
                interface="rest_api",
                action_name=action_name,
                status=status_str,
                input_params=input_params,
                output_summary=output_summary,
                error_message=error_msg,
                execution_time_ms=execution_time_ms,
                ip_address=ip,
                user_agent=user_agent
            )
        except Exception as e:
            logger.warning(f"Failed to record UserActivityLog in middleware: {e}")

        return response
