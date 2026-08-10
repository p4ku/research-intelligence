import hashlib
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from research_intelligence.models import APIKey, Workspace

User = get_user_model()

class APIKeyAdminTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="test_admin_user",
            email="admin@example.com",
            password="adminpassword"
        )
        self.workspace = Workspace.objects.create(
            name="Test Workspace",
            abstract_acceptance_criteria="Accept if...",
            abstract_rejection_criteria="Reject if..."
        )
        self.api_key = APIKey.objects.create(
            name="Test Key",
            key_id="test_key_id",
            user=self.user,
            workspace=self.workspace
        )
        self.api_key.set_secret("oldsecret")
        self.api_key.save()
        self.client.force_login(self.user)

    def test_admin_change_form_renders(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "⚡ Generate & Show New Secret")
        self.assertContains(response, "New Secret Key")

    def test_admin_save_custom_secret(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        data = {
            'name': 'Updated Key Name',
            'key_id': self.api_key.key_id,
            'hashed_secret': self.api_key.hashed_secret,
            'is_active': 'on',
            'scopes': '[]',
            'user': self.user.id,
            'workspace': self.workspace.id,
            'new_secret': 'new_custom_secret',
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.name, 'Updated Key Name')
        self.assertTrue(self.api_key.check_secret('new_custom_secret'))
        
        messages = list(response.context['messages'])
        self.assertTrue(any("API Key secret successfully configured!" in str(m) for m in messages))

    def test_admin_save_blank_keeps_secret(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        data = {
            'name': 'Updated Key Name 2',
            'key_id': self.api_key.key_id,
            'hashed_secret': self.api_key.hashed_secret,
            'is_active': 'on',
            'scopes': '[]',
            'user': self.user.id,
            'workspace': self.workspace.id,
            'new_secret': '', # blank
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.name, 'Updated Key Name 2')
        self.assertTrue(self.api_key.check_secret('oldsecret'))

    def test_admin_generate_secret_view(self):
        url = reverse('admin:generate-apikey-secret', args=[self.api_key.id])
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        # Verify secret is updated (should no longer be oldsecret)
        self.assertFalse(self.api_key.check_secret('oldsecret'))
        
        # Check success message shows the new secret key
        messages = list(response.context['messages'])
        self.assertTrue(any("Successfully generated a new secret for API Key" in str(m) for m in messages))
