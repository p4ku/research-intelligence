from rest_framework.views import exception_handler
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Standardized REST API exception handler.
    Ensures consistent error envelope containing status_code, error message,
    and granular field validation errors while preserving backwards compatibility.
    """
    response = exception_handler(exc, context)

    if response is not None:
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
