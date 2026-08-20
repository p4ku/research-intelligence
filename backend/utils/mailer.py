# Re-export mailer functions from research_intelligence.utils.mailer
from research_intelligence.utils.mailer import send_mailgun_message, send_mail

__all__ = ['send_mailgun_message', 'send_mail']
