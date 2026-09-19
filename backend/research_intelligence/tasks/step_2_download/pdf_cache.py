import hashlib
import logging
from django.db.models import Q, F
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Paper, DocumentRegistry
from ..constants import SourceDatabase

logger = logging.getLogger(__name__)


def find_in_document_registry(paper: Paper) -> DocumentRegistry | None:
    """
    Looks up a paper in the global DocumentRegistry using indexed fields:
    1. sha256_hash (Exact Hash)
    2. doi (Digital Object Identifier)
    3. arxiv_id (arXiv repository ID)
    4. source_url (Public article/patent landing page)
    """
    lookup_q = None
    if paper.hash_id:
        lookup_q = Q(sha256_hash=paper.hash_id)
    if paper.doi:
        lookup_q = (lookup_q | Q(doi=paper.doi)) if lookup_q else Q(doi=paper.doi)
    if paper.arxiv_id:
        lookup_q = (lookup_q | Q(arxiv_id=paper.arxiv_id)) if lookup_q else Q(arxiv_id=paper.arxiv_id)
    if paper.source_url:
        lookup_q = (lookup_q | Q(source_url=paper.source_url)) if lookup_q else Q(source_url=paper.source_url)

    if not lookup_q:
        return None

    return (
        DocumentRegistry.objects.filter(lookup_q)
        .filter(
            (Q(canonical_pdf_path__isnull=False) & ~Q(canonical_pdf_path=""))
            | (Q(canonical_ocr_md_path__isnull=False) & ~Q(canonical_ocr_md_path=""))
        )
        .first()
    )


def register_document_markdown(
    paper: Paper,
    file_bytes: bytes,
    ocr_provider: str = "google_patents_html",
    run_storage_path: str | None = None,
) -> DocumentRegistry:
    """
    Registers a newly downloaded or ingested Markdown document (e.g. Google Patents full text)
    into the global DocumentRegistry.
    Saves a persistent canonical copy under `cache/documents/{sha256_hash}/document.md`.
    """
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    canonical_cache_path = f"cache/documents/{sha256_hash}/document.md"

    if not default_storage.exists(canonical_cache_path):
        default_storage.save(canonical_cache_path, ContentFile(file_bytes))

    doc_reg = None
    if paper.source_url:
        doc_reg = DocumentRegistry.objects.filter(source_url=paper.source_url).first()
    if not doc_reg:
        doc_reg = DocumentRegistry.objects.filter(sha256_hash=sha256_hash).first()

    if not doc_reg:
        doc_reg = DocumentRegistry.objects.create(
            sha256_hash=sha256_hash,
            doi=paper.doi,
            arxiv_id=paper.arxiv_id,
            source_url=paper.source_url,
            title=paper.title,
            primary_source=SourceDatabase.for_paper(paper),
            canonical_pdf_path="",
            pdf_file_size_bytes=0,
            ocr_provider=ocr_provider,
            canonical_ocr_md_path=canonical_cache_path,
            access_count=1,
            meta=paper.meta or {},
        )
    else:
        updates = []
        if not doc_reg.canonical_ocr_md_path or not default_storage.exists(doc_reg.canonical_ocr_md_path):
            doc_reg.canonical_ocr_md_path = canonical_cache_path
            updates.append("canonical_ocr_md_path")
        if not doc_reg.ocr_provider or doc_reg.ocr_provider != ocr_provider:
            doc_reg.ocr_provider = ocr_provider
            updates.append("ocr_provider")
        if paper.source_url and not doc_reg.source_url:
            doc_reg.source_url = paper.source_url
            updates.append("source_url")
        if paper.title and (not doc_reg.title or doc_reg.title == "Untitled"):
            doc_reg.title = paper.title
            updates.append("title")
        if paper.meta and not doc_reg.meta:
            doc_reg.meta = paper.meta
            updates.append("meta")
        if paper.document_registry_id != doc_reg.id:
            doc_reg.access_count = F('access_count') + 1
            updates.append("access_count")
        if updates:
            doc_reg.save(update_fields=updates)
            doc_reg.refresh_from_db(fields=['access_count'])

    # Link Paper instance and sync meta if needed
    paper.document_registry = doc_reg
    paper_updates = ['document_registry']
    if not paper.meta and doc_reg.meta:
        paper.meta = doc_reg.meta
        paper_updates.append('meta')
    paper.save(update_fields=paper_updates)
    return doc_reg


def register_document_pdf(paper: Paper, file_bytes: bytes, run_storage_path: str | None = None) -> DocumentRegistry:
    """
    Registers a newly downloaded or ingested PDF binary into the global DocumentRegistry.
    Saves a persistent canonical copy under `cache/documents/{sha256_hash}/original.pdf`.
    """
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    canonical_cache_path = f"cache/documents/{sha256_hash}/original.pdf"

    if not default_storage.exists(canonical_cache_path):
        default_storage.save(canonical_cache_path, ContentFile(file_bytes))

    doc_reg, created = DocumentRegistry.objects.get_or_create(
        sha256_hash=sha256_hash,
        defaults={
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "source_url": paper.source_url,
            "title": paper.title,
            "primary_source": SourceDatabase.for_paper(paper),
            "canonical_pdf_path": canonical_cache_path,
            "pdf_file_size_bytes": len(file_bytes),
            "access_count": 1,
            "meta": paper.meta or {}
        }
    )

    if not created:
        updates = []
        if not doc_reg.canonical_pdf_path or not default_storage.exists(doc_reg.canonical_pdf_path):
            doc_reg.canonical_pdf_path = canonical_cache_path
            doc_reg.pdf_file_size_bytes = len(file_bytes)
            updates.extend(["canonical_pdf_path", "pdf_file_size_bytes"])
        if paper.doi and not doc_reg.doi:
            doc_reg.doi = paper.doi
            updates.append("doi")
        if paper.arxiv_id and not doc_reg.arxiv_id:
            doc_reg.arxiv_id = paper.arxiv_id
            updates.append("arxiv_id")
        if paper.source_url and not doc_reg.source_url:
            doc_reg.source_url = paper.source_url
            updates.append("source_url")
        if paper.meta and not doc_reg.meta:
            doc_reg.meta = paper.meta
            updates.append("meta")
        if paper.document_registry_id != doc_reg.id:
            doc_reg.access_count = F('access_count') + 1
            updates.append("access_count")
        if updates:
            doc_reg.save(update_fields=updates)
            doc_reg.refresh_from_db(fields=['access_count'])

    # Link Paper instance and sync meta if needed
    paper.document_registry = doc_reg
    paper_updates = ['document_registry']
    if not paper.meta and doc_reg.meta:
        paper.meta = doc_reg.meta
        paper_updates.append('meta')
    paper.save(update_fields=paper_updates)
    return doc_reg


def try_reuse_cached_pdf(paper: Paper, target_path: str, title_snippet: str = "") -> dict | None:
    """
    Cross-Workspace / Cross-Run PDF Cache Reuse (Zero-Network Fast Path).
    1. Checks the global `DocumentRegistry` index.
    2. If found, reads from the canonical storage path and writes to `target_path`.
    3. Atomically increments `access_count` in `DocumentRegistry`.
    4. Falls back to cross-Paper search if DocumentRegistry record is missing.
    """
    # 1. Primary Lookup via DocumentRegistry
    doc_reg = find_in_document_registry(paper)
    if doc_reg and doc_reg.canonical_pdf_path and default_storage.exists(doc_reg.canonical_pdf_path):
        try:
            with default_storage.open(doc_reg.canonical_pdf_path, 'rb') as src_file:
                file_bytes = src_file.read()

            if file_bytes and len(file_bytes) > 0:
                if default_storage.exists(target_path):
                    default_storage.delete(target_path)
                saved_path = default_storage.save(target_path, ContentFile(file_bytes))
                paper.original_pdf_path = saved_path
                paper.document_registry = doc_reg
                paper_fields = ['original_pdf_path', 'document_registry']
                if not paper.meta and doc_reg.meta:
                    paper.meta = doc_reg.meta
                    paper_fields.append('meta')
                elif paper.meta and not doc_reg.meta:
                    doc_reg.meta = paper.meta
                    doc_reg.save(update_fields=['meta'])
                paper.save(update_fields=paper_fields)

                # Increment registry access count
                DocumentRegistry.objects.filter(pk=doc_reg.pk).update(access_count=F('access_count') + 1)
                doc_reg.refresh_from_db(fields=['access_count', 'last_accessed_at'])

                size_bytes = len(file_bytes)
                size_kb = size_bytes / 1024
                logger.info(
                    f"⚡ [REGISTRY CACHE HIT] Reused cached PDF [{size_kb:.1f} KB] (Hits: {doc_reg.access_count}) "
                    f"from '{doc_reg.canonical_pdf_path}' -> '{saved_path}' (Paper: '{title_snippet}...')",
                )
                return {
                    "status": "downloaded",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "size_bytes": size_bytes,
                    "size_kb": round(size_kb, 1),
                    "storage_path": saved_path,
                    "from_cache": True,
                    "cached_from": doc_reg.canonical_pdf_path,
                    "registry_id": str(doc_reg.id),
                    "access_count": doc_reg.access_count
                }
        except Exception as e:
            logger.warning(f"Failed to copy from DocumentRegistry '{doc_reg.canonical_pdf_path}': {e}")

    # 2. Secondary Fallback: Direct Paper Table Lookup
    lookup_q = None
    if paper.hash_id:
        lookup_q = Q(hash_id=paper.hash_id)
    if paper.doi:
        lookup_q = (lookup_q | Q(doi=paper.doi)) if lookup_q else Q(doi=paper.doi)
    if paper.arxiv_id:
        lookup_q = (lookup_q | Q(arxiv_id=paper.arxiv_id)) if lookup_q else Q(arxiv_id=paper.arxiv_id)

    if not lookup_q:
        return None

    cached_paper = (
        Paper.objects.filter(lookup_q)
        .exclude(id=paper.id)
        .exclude(original_pdf_path__startswith="http://")
        .exclude(original_pdf_path__startswith="https://")
        .exclude(original_pdf_path="")
        .exclude(original_pdf_path__isnull=True)
        .first()
    )

    if not cached_paper or not default_storage.exists(cached_paper.original_pdf_path):
        return None

    try:
        with default_storage.open(cached_paper.original_pdf_path, 'rb') as src_file:
            file_bytes = src_file.read()

        if file_bytes and len(file_bytes) > 0:
            if default_storage.exists(target_path):
                default_storage.delete(target_path)
            saved_path = default_storage.save(target_path, ContentFile(file_bytes))
            paper.original_pdf_path = saved_path
            paper.save(update_fields=['original_pdf_path'])

            # Register in DocumentRegistry for future fastpath lookups
            doc_reg = register_document_pdf(paper, file_bytes)

            size_bytes = len(file_bytes)
            size_kb = size_bytes / 1024
            logger.info(
                f"⚡ [CACHE REUSE] Reused cached PDF [{size_kb:.1f} KB] from "
                f"'{cached_paper.original_pdf_path}' -> saved to: '{saved_path}' (Paper: '{title_snippet}...')",
            )
            return {
                "status": "downloaded",
                "paper_id": str(paper.id),
                "title": paper.title,
                "size_bytes": size_bytes,
                "size_kb": round(size_kb, 1),
                "storage_path": saved_path,
                "from_cache": True,
                "cached_from": cached_paper.original_pdf_path,
                "registry_id": str(doc_reg.id) if doc_reg else None
            }
    except Exception as e:
        logger.warning(f"Failed to copy cached PDF from '{cached_paper.original_pdf_path}': {e}")
        return None

    return None


def try_reuse_cached_markdown(paper: Paper, target_path: str, title_snippet: str = "") -> dict | None:
    """
    Cross-Workspace / Cross-Run Markdown Cache Reuse (Zero-Network Fast Path).
    1. Checks the global `DocumentRegistry` index.
    2. If found, reads from canonical_ocr_md_path and writes to `target_path`.
    3. Atomically increments `access_count` in `DocumentRegistry`.
    4. Falls back to cross-Paper search if DocumentRegistry record is missing.
    """
    doc_reg = find_in_document_registry(paper)
    if doc_reg and doc_reg.canonical_ocr_md_path and default_storage.exists(doc_reg.canonical_ocr_md_path):
        try:
            with default_storage.open(doc_reg.canonical_ocr_md_path, 'rb') as src_file:
                file_bytes = src_file.read()

            if file_bytes and len(file_bytes) > 0:
                if default_storage.exists(target_path):
                    default_storage.delete(target_path)
                saved_path = default_storage.save(target_path, ContentFile(file_bytes))
                paper.converted_md_path = saved_path
                paper.document_registry = doc_reg
                paper_fields = ['converted_md_path', 'document_registry']
                if not paper.meta and doc_reg.meta:
                    paper.meta = doc_reg.meta
                    paper_fields.append('meta')
                elif paper.meta and not doc_reg.meta:
                    doc_reg.meta = paper.meta
                    doc_reg.save(update_fields=['meta'])
                paper.save(update_fields=paper_fields)

                DocumentRegistry.objects.filter(pk=doc_reg.pk).update(access_count=F('access_count') + 1)
                doc_reg.refresh_from_db(fields=['access_count', 'last_accessed_at'])

                size_bytes = len(file_bytes)
                size_kb = size_bytes / 1024
                logger.info(
                    f"⚡ [REGISTRY CACHE HIT] Reused cached Markdown [{size_kb:.1f} KB] (Hits: {doc_reg.access_count}) "
                    f"from '{doc_reg.canonical_ocr_md_path}' -> '{saved_path}' (Paper: '{title_snippet}...')",
                )
                return {
                    "status": "downloaded",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "size_bytes": size_bytes,
                    "size_kb": round(size_kb, 1),
                    "storage_path": saved_path,
                    "format": "markdown",
                    "from_cache": True,
                    "cached_from": doc_reg.canonical_ocr_md_path,
                    "registry_id": str(doc_reg.id),
                    "access_count": doc_reg.access_count
                }
        except Exception as e:
            logger.warning(f"Failed to copy cached Markdown from DocumentRegistry '{doc_reg.canonical_ocr_md_path}': {e}")

    # 2. Secondary Fallback: Direct Paper Table Lookup
    lookup_q = None
    if paper.hash_id:
        lookup_q = Q(hash_id=paper.hash_id)
    if paper.doi:
        lookup_q = (lookup_q | Q(doi=paper.doi)) if lookup_q else Q(doi=paper.doi)
    if paper.arxiv_id:
        lookup_q = (lookup_q | Q(arxiv_id=paper.arxiv_id)) if lookup_q else Q(arxiv_id=paper.arxiv_id)
    if paper.source_url:
        lookup_q = (lookup_q | Q(source_url=paper.source_url)) if lookup_q else Q(source_url=paper.source_url)

    if not lookup_q:
        return None

    cached_paper = (
        Paper.objects.filter(lookup_q)
        .exclude(id=paper.id)
        .exclude(converted_md_path__isnull=True)
        .exclude(converted_md_path="")
        .first()
    )

    if not cached_paper or not default_storage.exists(cached_paper.converted_md_path):
        return None

    try:
        with default_storage.open(cached_paper.converted_md_path, 'rb') as src_file:
            file_bytes = src_file.read()

        if file_bytes and len(file_bytes) > 0:
            if default_storage.exists(target_path):
                default_storage.delete(target_path)
            saved_path = default_storage.save(target_path, ContentFile(file_bytes))
            paper.converted_md_path = saved_path
            paper.save(update_fields=['converted_md_path'])

            doc_reg = register_document_markdown(
                paper,
                file_bytes,
                ocr_provider=SourceDatabase.ocr_provider_for(paper)
            )

            size_bytes = len(file_bytes)
            size_kb = size_bytes / 1024
            logger.info(
                f"⚡ [CACHE REUSE] Reused cached Markdown [{size_kb:.1f} KB] from "
                f"'{cached_paper.converted_md_path}' -> saved to: '{saved_path}' (Paper: '{title_snippet}...')",
            )
            return {
                "status": "downloaded",
                "paper_id": str(paper.id),
                "title": paper.title,
                "size_bytes": size_bytes,
                "size_kb": round(size_kb, 1),
                "storage_path": saved_path,
                "format": "markdown",
                "from_cache": True,
                "cached_from": cached_paper.converted_md_path,
                "registry_id": str(doc_reg.id) if doc_reg else None
            }
    except Exception as e:
        logger.warning(f"Failed to copy cached Markdown from '{cached_paper.converted_md_path}': {e}")
        return None

    return None

