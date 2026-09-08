# utils/mailer.py
import logging
from typing import Optional, Tuple, Union, Dict, List
import requests
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_mailgun_message(
        to_email: str,
        subject: str,
        from_email: Optional[str] = None,
        template_name: Optional[str] = None,
        context: Optional[Dict] = None,
        text: Optional[str] = None,
        html: Optional[str] = None,
        timeout: int = 10,
        files: Optional[Union[Dict, List]] = None,
) -> Tuple[bool, Union[dict, str]]:
    """
    Send an email via Mailgun.

    - Reads MAILGUN_API_URL, MAILGUN_SENDER_DOMAIN and MAILGUN_API_KEY from settings.
    - If template_name provided, will render both <template_name>.html and <template_name>.txt
      from the Django template loader (context must be provided for rendering).
    - Returns (success: bool, response_or_error: dict or error-string).
    """
    from research_intelligence.features import is_feature_enabled, Feature

    if not is_feature_enabled(Feature.EMAIL_NOTIFICATIONS):
        return True, {"message": "Email sending suppressed (feature disabled)", "suppressed": True}

    mailgun_url = getattr(settings, 'MAILGUN_API_URL', 'https://api.eu.mailgun.net/v3')
    mailgun_domain = getattr(settings, 'MAILGUN_SENDER_DOMAIN', 'soinventive.co.uk')
    api_url = f"{mailgun_url}/{mailgun_domain}/messages"
    api_key = f"{getattr(settings, 'MAILGUN_API_KEY', '')}"

    if not getattr(settings, 'MAILGUN_API_KEY', ''):
        err = "mailgun settings not configured (MAILGUN_API_URL / MAILGUN_API_KEY)"
        logger.error(err)
        return False, err

    from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', f"no-reply@{mailgun_domain}")
    if template_name:
        if context is None:
            context = {}
        try:
            # Render templates if they exist; render_to_string will raise if template missing.
            rendered_html = render_to_string(f"{template_name}.html", context)
        except Exception:
            rendered_html = None
        try:
            rendered_text = render_to_string(f"{template_name}.txt", context)
        except Exception:
            rendered_text = None

        # prefer provided html/text if set explicitly
        html = html or rendered_html
        text = text or rendered_text

    data = {
        "from": from_email,
        "to": to_email,
        "subject": subject,
    }
    if text:
        data["text"] = text
    if html:
        data["html"] = html

    try:
        resp = requests.post(api_url, auth=("api", api_key), data=data, timeout=timeout, files=files)
        logger.debug(data)
        resp.raise_for_status()
        # Mailgun returns json like {"message":"Queued. Thank you.","id":"<...>"}
        try:
            return True, resp.json()
        except Exception:
            return True, {"status_code": resp.status_code, "text": resp.text}
    except Exception as exc:
        logger.exception("Failed to send email to %s", to_email)
        return False, str(exc)


def send_mail(subject: str, message: str, from_email: str, recipient_list: List[str], fail_silently: bool = False, html_message: str = None):
    """
    Django send_mail compatible wrapper for send_mailgun_message.
    """
    from research_intelligence.features import is_feature_enabled, Feature

    if not is_feature_enabled(Feature.EMAIL_NOTIFICATIONS):
        return 0

    success_all = True
    for email in recipient_list:
        success, _ = send_mailgun_message(
            to_email=email,
            subject=subject,
            from_email=from_email,
            text=message,
            html=html_message
        )
        if not success:
            success_all = False
            if not fail_silently:
                raise Exception(f"Failed to send email to {email}")
    return 1 if success_all else 0
