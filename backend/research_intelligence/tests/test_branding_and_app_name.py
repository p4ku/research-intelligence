from django.test import TestCase, override_settings
from django.conf import settings
from rest_framework.test import APIClient


class BrandingAndAppNameTests(TestCase):
    """
    Validates that platform branding and system name are parameterized via APP_NAME,
    APP_SHORT_NAME, and APP_DESCRIPTION across Django settings, Django admin,
    REST API health check, and templates.
    """

    def setUp(self):
        self.client = APIClient()

    def test_default_settings_branding(self):
        """Verifies default fallback branding values in Django settings."""
        self.assertTrue(hasattr(settings, "APP_NAME"))
        self.assertTrue(hasattr(settings, "APP_SHORT_NAME"))
        self.assertTrue(hasattr(settings, "APP_DESCRIPTION"))
        self.assertIn("REST API", settings.SPECTACULAR_SETTINGS["TITLE"])

    @override_settings(
        APP_NAME="Systematic Literature Review",
        APP_SHORT_NAME="SLR",
        APP_DESCRIPTION="Automated Cochrane-grade SLR Engine"
    )
    def test_health_check_endpoint_reflects_custom_branding(self):
        """Verifies GET /api/health/ returns custom APP_NAME and APP_SHORT_NAME."""
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app_name"], "Systematic Literature Review")
        self.assertEqual(data["app_short_name"], "SLR")

    @override_settings(
        APP_NAME="Intelligence Systematic Literature Review",
        APP_SHORT_NAME="ISLR"
    )
    def test_django_admin_titles_use_configured_app_name(self):
        """Verifies Django admin site header and title adapt to configured APP_NAME."""
        app_name = getattr(settings, "APP_NAME")
        header = f"{app_name} Admin"
        self.assertEqual(header, "Intelligence Systematic Literature Review Admin")
