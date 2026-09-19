import hashlib
from django.db import migrations
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile


def backfill_markdown_document_registry(apps, schema_editor):
    """
    Backfills DocumentRegistry records for existing papers that were downloaded as Markdown
    (such as Google Patents full text) without a DocumentRegistry link.
    """
    Paper = apps.get_model('research_intelligence', 'Paper')
    DocumentRegistry = apps.get_model('research_intelligence', 'DocumentRegistry')

    unlinked_papers = (
        Paper.objects.filter(document_registry__isnull=True)
        .exclude(converted_md_path__isnull=True)
        .exclude(converted_md_path="")
    )

    for paper in unlinked_papers.iterator(chunk_size=200):
        if not paper.converted_md_path or not default_storage.exists(paper.converted_md_path):
            continue
        try:
            with default_storage.open(paper.converted_md_path, 'rb') as f:
                file_bytes = f.read()
            if not file_bytes:
                continue

            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            canonical_cache_path = f"cache/documents/{sha256_hash}/document.md"
            if not default_storage.exists(canonical_cache_path):
                default_storage.save(canonical_cache_path, ContentFile(file_bytes))

            doc_reg = None
            if paper.source_url:
                doc_reg = DocumentRegistry.objects.filter(source_url=paper.source_url).first()
            if not doc_reg:
                doc_reg = DocumentRegistry.objects.filter(sha256_hash=sha256_hash).first()

            ocr_provider = "google_patents_html" if paper.source_database == "google_patents" else "markdown"

            if not doc_reg:
                doc_reg = DocumentRegistry.objects.create(
                    sha256_hash=sha256_hash,
                    doi=paper.doi,
                    arxiv_id=paper.arxiv_id,
                    source_url=paper.source_url,
                    title=paper.title,
                    primary_source=paper.source_database or "google_patents",
                    canonical_pdf_path="",
                    pdf_file_size_bytes=0,
                    ocr_provider=ocr_provider,
                    canonical_ocr_md_path=canonical_cache_path,
                    access_count=1,
                    meta=paper.meta or {},
                )
            else:
                updates = []
                if not doc_reg.canonical_ocr_md_path:
                    doc_reg.canonical_ocr_md_path = canonical_cache_path
                    updates.append("canonical_ocr_md_path")
                if not doc_reg.ocr_provider:
                    doc_reg.ocr_provider = ocr_provider
                    updates.append("ocr_provider")
                if paper.source_url and not doc_reg.source_url:
                    doc_reg.source_url = paper.source_url
                    updates.append("source_url")
                if paper.meta and not doc_reg.meta:
                    doc_reg.meta = paper.meta
                    updates.append("meta")
                if updates:
                    doc_reg.save(update_fields=updates)

            paper.document_registry = doc_reg
            paper.save(update_fields=['document_registry'])
        except Exception:
            pass


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('research_intelligence', '0077_scraper_api_key_alter_scraper_provider'),
    ]

    operations = [
        migrations.RunPython(backfill_markdown_document_registry, reverse_code=noop_reverse),
    ]
