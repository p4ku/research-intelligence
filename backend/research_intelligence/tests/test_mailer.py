from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from research_intelligence.utils.mailer import send_mailgun_message, send_mail
from utils.mailer import send_mailgun_message as utils_send_mailgun_message


class MailgunMailerTests(TestCase):

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
        DEFAULT_FROM_EMAIL="noreply@soinventive.co.uk",
    )
    @patch("requests.post")
    def test_send_mailgun_message_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "<20260820@soinventive.co.uk>", "message": "Queued. Thank you."}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Research Pipeline Briefing",
            text="Your systematic literature review is ready.",
            html="<p>Your systematic literature review is ready.</p>"
        )

        self.assertTrue(success)
        self.assertEqual(res["message"], "Queued. Thank you.")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.eu.mailgun.net/v3/soinventive.co.uk/messages")
        self.assertEqual(kwargs["auth"], ("api", "key-test123456"))
        self.assertEqual(kwargs["data"]["to"], "client@example.com")
        self.assertEqual(kwargs["data"]["from"], "noreply@soinventive.co.uk")
        self.assertEqual(kwargs["data"]["subject"], "Research Pipeline Briefing")
        self.assertEqual(kwargs["data"]["text"], "Your systematic literature review is ready.")
        self.assertEqual(kwargs["data"]["html"], "<p>Your systematic literature review is ready.</p>")

    @override_settings(MAILGUN_API_KEY="")
    def test_send_mailgun_message_missing_key(self):
        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Test Subject",
            text="Hello"
        )
        self.assertFalse(success)
        self.assertIn("mailgun settings not configured", res)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
    )
    @patch("requests.post")
    def test_send_mailgun_message_http_error(self, mock_post):
        mock_post.side_effect = Exception("Connection Timeout")

        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Error Subject",
            text="Test"
        )
        self.assertFalse(success)
        self.assertIn("Connection Timeout", res)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
        DEFAULT_FROM_EMAIL="alerts@soinventive.co.uk",
    )
    @patch("research_intelligence.utils.mailer.send_mailgun_message")
    def test_send_mail_wrapper(self, mock_send_mailgun):
        mock_send_mailgun.return_value = (True, {"message": "Queued."})

        sent_count = send_mail(
            subject="Weekly Alert",
            message="Alert message",
            from_email="alerts@soinventive.co.uk",
            recipient_list=["user1@example.com", "user2@example.com"],
            fail_silently=False
        )

        self.assertEqual(sent_count, 1)
        self.assertEqual(mock_send_mailgun.call_count, 2)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
    )
    @patch("research_intelligence.utils.mailer.send_mailgun_message")
    def test_send_mail_wrapper_failure(self, mock_send_mailgun):
        mock_send_mailgun.return_value = (False, "Mailgun 401 Unauthorized")

        # When fail_silently is False, raises Exception
        with self.assertRaises(Exception):
            send_mail(
                subject="Weekly Alert",
                message="Alert message",
                from_email="alerts@soinventive.co.uk",
                recipient_list=["user1@example.com"],
                fail_silently=False
            )

        # When fail_silently is True, returns 0
        sent_count = send_mail(
            subject="Weekly Alert",
            message="Alert message",
            from_email="alerts@soinventive.co.uk",
            recipient_list=["user1@example.com"],
            fail_silently=True
        )
        self.assertEqual(sent_count, 0)

    def test_utils_reexport(self):
        self.assertIs(send_mailgun_message, utils_send_mailgun_message)
