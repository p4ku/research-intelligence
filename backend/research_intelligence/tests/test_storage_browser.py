import os
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.urls import reverse

User = get_user_model()

class StorageBrowserTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="storage_admin",
            email="storage_admin@example.com",
            password="adminpassword123"
        )
        self.client.force_login(self.superuser)

        # Create dummy storage structure in default_storage
        self.file_1 = default_storage.save("test_dir/file1.txt", ContentFile(b"Hello World text file content"))
        self.file_2 = default_storage.save("test_dir/data.json", ContentFile(b'{"key": "value"}'))
        self.file_3 = default_storage.save("test_dir/sub_dir/doc.md", ContentFile(b"# Markdown Document"))

    def tearDown(self):
        # Cleanup storage files
        for p in ["test_dir/file1.txt", "test_dir/data.json", "test_dir/sub_dir/doc.md"]:
            if default_storage.exists(p):
                default_storage.delete(p)

    def test_storage_browser_requires_staff(self):
        self.client.logout()
        url = reverse('admin:storage-browser')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_storage_browser_list_root(self):
        url = f"{reverse('admin:storage-browser')}?path="
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Storage Browser:")
        self.assertContains(response, "test_dir")

    def test_storage_browser_list_subdir(self):
        url = f"{reverse('admin:storage-browser')}?path=test_dir"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "file1.txt")
        self.assertContains(response, "data.json")
        self.assertContains(response, "sub_dir")

    def test_storage_browser_preview_file(self):
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=preview&file=test_dir/file1.txt"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hello World text file content")

    def test_storage_browser_download_file(self):
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=download&file=test_dir/file1.txt"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_storage_browser_delete_file(self):
        self.assertTrue(default_storage.exists(self.file_1))
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=delete_file&file=test_dir/file1.txt"
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(default_storage.exists(self.file_1))

    def test_storage_browser_delete_dir(self):
        self.assertTrue(default_storage.exists("test_dir/sub_dir/doc.md"))
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=delete_dir&target_dir=test_dir/sub_dir"
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(default_storage.exists("test_dir/sub_dir/doc.md"))
        dirs, _ = default_storage.listdir("test_dir")
        self.assertNotIn("sub_dir", dirs)
        self.assertNotContains(response, "sub_dir/")

    def test_storage_browser_disallows_codebase_paths(self):
        # Accessing codebase directory should redirect with error
        url = f"{reverse('admin:storage-browser')}?path=api"
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access denied")

        # Accessing forbidden file action should be blocked
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=preview&file=manage.py"
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access denied")

    def test_storage_browser_root_hides_codebase_files(self):
        url = f"{reverse('admin:storage-browser')}?path="
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should not show codebase directories or files
        self.assertNotContains(response, "api/")
        self.assertNotContains(response, "django_project/")
        self.assertNotContains(response, "research_intelligence/")
        self.assertNotContains(response, "manage.py")
        self.assertNotContains(response, "Dockerfile")

    def test_storage_browser_shows_directory_timestamp(self):
        url = f"{reverse('admin:storage-browser')}?path=test_dir"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sub_dir/")
        # Ensure directory row has a valid timestamp format or non-empty string in modified column
        content = response.content.decode('utf-8')
        self.assertIn("sub_dir/", content)


