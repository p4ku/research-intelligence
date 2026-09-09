from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Standardized REST API exception handler.
    Ensures consistent error envelope containing status_code, error message,
    and granular field validation errors while preserving backwards compatibility.
    Handles both DRF APIExceptions and uncaught server errors with Sentry and logging.
    """
    response = exception_handler(exc, context)

    if response is None:
        view_name = context.get('view').__class__.__name__ if context and 'view' in context else 'unknown'
        logger.exception("Unhandled API exception in %s: %s", view_name, exc)

        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass

        return Response(
            {
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": "An internal server error occurred.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    custom_data = {
        "status_code": response.status_code,
    }
    if isinstance(response.data, dict):
        if "error" in response.data:
            custom_data["error"] = response.data["error"]
        elif "detail" in response.data:
            custom_data["error"] = str(response.data["detail"])
        else:
            first_key = next(iter(response.data))
            val = response.data[first_key]
            first_msg = val[0] if isinstance(val, (list, tuple)) and len(val) > 0 else str(val)
            custom_data["error"] = f"{first_key}: {first_msg}" if first_key != "non_field_errors" else str(first_msg)

        for k, v in response.data.items():
            custom_data[k] = v
    elif isinstance(response.data, list):
        custom_data["error"] = str(response.data[0]) if response.data else "An error occurred."
        custom_data["errors"] = response.data
    else:
        custom_data["error"] = str(response.data)

    response.data = custom_data

    return response
