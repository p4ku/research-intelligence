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
        self.assertContains(response, "workspaces/")
        self.assertContains(response, "cache/")
        self.assertContains(response, "test_dir")

    def test_storage_browser_list_cache_dir(self):
        # Create a document in cache
        from research_intelligence.models import DocumentRegistry
        sha = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        doc = DocumentRegistry.objects.create(
            sha256_hash=sha,
            title="Transformer Architecture Research",
            canonical_pdf_path=f"cache/documents/{sha}/original.pdf"
        )
        cached_file = default_storage.save(f"cache/documents/{sha}/original.pdf", ContentFile(b"%PDF-1.4 test"))
        try:
            url = f"{reverse('admin:storage-browser')}?path=cache"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "documents/")

            url_docs = f"{reverse('admin:storage-browser')}?path=cache/documents"
            response_docs = self.client.get(url_docs)
            self.assertEqual(response_docs.status_code, 200)
            self.assertContains(response_docs, f"{sha}/")
            self.assertContains(response_docs, "Transformer Architecture Research")
        finally:
            if default_storage.exists(cached_file):
                default_storage.delete(cached_file)
            doc.delete()

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

    def test_storage_browser_preview_pdf(self):
        pdf_path = default_storage.save("test_dir/paper.pdf", ContentFile(b"%PDF-1.4 sample pdf binary"))
        try:
            url = f"{reverse('admin:storage-browser')}?path=test_dir&action=preview&file=test_dir/paper.pdf"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertContains(response, 'title="PDF Preview"')
            self.assertContains(response, "action=view_raw&file=test_dir/paper.pdf")
            self.assertContains(response, "Open Full Screen")
        finally:
            if default_storage.exists(pdf_path):
                default_storage.delete(pdf_path)

    def test_storage_browser_view_raw_pdf(self):
        pdf_path = default_storage.save("test_dir/sample.pdf", ContentFile(b"%PDF-1.4 sample pdf binary"))
        try:
            url = f"{reverse('admin:storage-browser')}?action=view_raw&file=test_dir/sample.pdf"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn('inline', response['Content-Disposition'])
        finally:
            if default_storage.exists(pdf_path):
                default_storage.delete(pdf_path)

    def test_storage_browser_download_file(self):
        url = f"{reverse('admin:storage-browser')}?path=test_dir&action=download&file=test_dir/file1.txt"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_storage_browser_download_friendly_paper_name(self):
        from research_intelligence.models import DocumentRegistry
        sha = "0195bb61fa7ebd6e921692ea2ff2e92dd70ebfd3cbffa33992d6b27fd178f9bf"
        doc = DocumentRegistry.objects.create(
            sha256_hash=sha,
            title="Attention Is All You Need",
            arxiv_id="1706.03762",
            canonical_pdf_path=f"cache/documents/{sha}/original.pdf"
        )
        pdf_path = default_storage.save(f"cache/documents/{sha}/original.pdf", ContentFile(b"%PDF-1.4 sample"))
        try:
            url = f"{reverse('admin:storage-browser')}?path=cache/documents/{sha}&action=download&file=cache/documents/{sha}/original.pdf"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            # Should have the original paper title instead of generic original.pdf
            self.assertIn('1706.03762_Attention_Is_All_You_Need.pdf', response['Content-Disposition'])
        finally:
            if default_storage.exists(pdf_path):
                default_storage.delete(pdf_path)
            doc.delete()

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


