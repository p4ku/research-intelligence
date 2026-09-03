import time
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from django.db.models import Q
from research_intelligence.models import DocumentRegistry, Paper
from research_intelligence.scrapers.arxiv import ArxivScraperProvider


class Command(BaseCommand):
    help = "Gradually and politely backfills missing source metadata ('meta') for downloaded documents in DocumentRegistry and Paper."

    def add_arguments(self, parser):
        parser.add_argument(
            '--delay',
            type=float,
            default=3.5,
            help='Polite delay in seconds between external API requests (default: 3.5s for arXiv compliance).',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of arXiv IDs to query per request in id_list (default: 10, use 1 for strictly one-by-one).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of documents to process in this run (default: unlimited).',
        )
        parser.add_argument(
            '--source',
            choices=['all', 'arxiv', 'openalex'],
            default='all',
            help='Target repository to backfill from (default: all).',
        )
        parser.add_argument(
            '--target-id',
            type=str,
            default=None,
            help='Specific DocumentRegistry UUID or arxiv_id to backfill single document.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-fetching and overwriting meta even if already populated.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate queries and display matches without saving to database.',
        )

    def handle(self, *args, **options):
        delay = options['delay']
        batch_size = max(1, options['batch_size'])
        limit = options['limit']
        source = options['source']
        target_id = options['target_id']
        force = options['force']
        dry_run = options['dry_run']

        self.stdout.write(self.style.NOTICE("🔍 Starting Gentle Metadata Backfill..."))
        self.stdout.write(f"   ⚙️ Config: delay={delay}s, batch_size={batch_size}, source={source}, force={force}, dry_run={dry_run}")

        # 1. Base Queryset
        qs = DocumentRegistry.objects.all()
        if target_id:
            qs = qs.filter(Q(id__iexact=target_id) | Q(arxiv_id__iexact=target_id) | Q(doi__iexact=target_id))
        elif not force:
            qs = qs.filter(Q(meta__isnull=True) | Q(meta={}))

        total_pending = qs.count()
        self.stdout.write(self.style.NOTICE(f"   📊 Found {total_pending} documents eligible for metadata backfill."))

        if total_pending == 0:
            self.stdout.write(self.style.SUCCESS("✨ No documents require metadata backfill. All up to date!"))
            return

        total_updated = 0
        total_failed = 0
        total_skipped = 0
        start_time = time.time()

        scraper = ArxivScraperProvider()

        # 2. Process arXiv Documents
        if source in ['all', 'arxiv']:
            arxiv_docs = qs.exclude(Q(arxiv_id__isnull=True) | Q(arxiv_id=''))
            if limit:
                arxiv_docs = arxiv_docs[:limit]
            
            docs_list = list(arxiv_docs)
            total_arxiv = len(docs_list)
            self.stdout.write(self.style.NOTICE(f"\n📦 Processing {total_arxiv} arXiv documents (Batch size: {batch_size})..."))

            for chunk_start in range(0, total_arxiv, batch_size):
                chunk = docs_list[chunk_start:chunk_start + batch_size]
                id_map = {doc.arxiv_id.strip(): doc for doc in chunk if doc.arxiv_id}
                clean_ids = list(id_map.keys())

                if not clean_ids:
                    continue

                batch_num = (chunk_start // batch_size) + 1
                total_batches = (total_arxiv + batch_size - 1) // batch_size
                self.stdout.write(f"   ⏳ [Batch {batch_num}/{total_batches}] Requesting {len(clean_ids)} IDs from arXiv: {', '.join(clean_ids[:3])}{'...' if len(clean_ids) > 3 else ''}")

                entries_dict = self._fetch_arxiv_entries_batch(clean_ids, scraper)

                for arxiv_id, doc in id_map.items():
                    # Check exact match or base ID without version
                    base_id = arxiv_id.split('v')[0]
                    entry_meta = entries_dict.get(arxiv_id) or entries_dict.get(base_id)

                    if not entry_meta:
                        # Try case-insensitive or partial match
                        for k, v in entries_dict.items():
                            if k.lower().startswith(base_id.lower()) or base_id.lower().startswith(k.lower()):
                                entry_meta = v
                                break

                    if entry_meta:
                        if not dry_run:
                            doc.meta = entry_meta
                            doc.save(update_fields=['meta'])
                            # Sync to linked Paper instances
                            linked_updated = Paper.objects.filter(document_registry=doc).update(meta=entry_meta)
                            paper_note = f" (synced {linked_updated} papers)" if linked_updated else ""
                        else:
                            paper_note = " (dry-run)"

                        total_updated += 1
                        self.stdout.write(self.style.SUCCESS(f"      ✅ [{total_updated}] {arxiv_id}: '{doc.title[:45]}...'{paper_note}"))
                    else:
                        total_failed += 1
                        self.stdout.write(self.style.WARNING(f"      ⚠️ [{arxiv_id}] No entry returned by arXiv for '{doc.title[:45]}...'"))

                # Respectful rate limiting pause between batches
                if chunk_start + batch_size < total_arxiv:
                    time.sleep(delay)

        # 3. Process OpenAlex / DOI Documents (those without arXiv ID)
        if source in ['all', 'openalex']:
            remaining_limit = limit - total_updated if limit else None
            openalex_docs = qs.filter(Q(arxiv_id__isnull=True) | Q(arxiv_id='')).exclude(Q(doi__isnull=True) | Q(doi=''))
            if remaining_limit is not None and remaining_limit > 0:
                openalex_docs = openalex_docs[:remaining_limit]

            oa_list = list(openalex_docs)
            total_oa = len(oa_list)
            if total_oa > 0:
                self.stdout.write(self.style.NOTICE(f"\n🌐 Processing {total_oa} OpenAlex/DOI documents (one-by-one with polite delay)..."))
                for idx, doc in enumerate(oa_list, 1):
                    self.stdout.write(f"   ⏳ [{idx}/{total_oa}] Fetching OpenAlex for DOI '{doc.doi}' ('{doc.title[:40]}...')...")
                    oa_meta = self._fetch_openalex_entry(doc.doi, doc.title)
                    if oa_meta:
                        if not dry_run:
                            doc.meta = oa_meta
                            doc.save(update_fields=['meta'])
                            linked_updated = Paper.objects.filter(document_registry=doc).update(meta=oa_meta)
                            paper_note = f" (synced {linked_updated} papers)" if linked_updated else ""
                        else:
                            paper_note = " (dry-run)"

                        total_updated += 1
                        self.stdout.write(self.style.SUCCESS(f"      ✅ DOI {doc.doi} updated.{paper_note}"))
                    else:
                        total_failed += 1
                        self.stdout.write(self.style.WARNING(f"      ⚠️ DOI {doc.doi} not found in OpenAlex."))

                    if idx < total_oa:
                        time.sleep(max(1.0, delay))

        elapsed = round(time.time() - start_time, 1)
        self.stdout.write(self.style.NOTICE("\n=================================================="))
        self.stdout.write(self.style.SUCCESS(f"✨ Backfill Completed in {elapsed}s!"))
        self.stdout.write(f"   ✅ Successfully Updated: {total_updated}")
        self.stdout.write(f"   ⚠️ Failed/Not Found:    {total_failed}")
        self.stdout.write(f"   ⏭️ Skipped:             {total_skipped}")
        self.stdout.write(self.style.NOTICE("=================================================="))

    def _fetch_arxiv_entries_batch(self, arxiv_ids: list[str], scraper: ArxivScraperProvider, retries: int = 3) -> dict[str, dict]:
        """
        Fetches metadata for a batch of arXiv IDs in a single HTTP request.
        Returns a dict mapping clean_arxiv_id -> meta dict.
        """
        id_query = ",".join(arxiv_ids)
        encoded_ids = urllib.parse.quote(id_query, safe=",-_.")
        url = f"https://export.arxiv.org/api/query?id_list={encoded_ids}&max_results={len(arxiv_ids)}"

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'SchwarzResearchIntelligence/1.0 (mailto:research@schwarz-it.com)'}
        )

        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw_xml = resp.read()
                root = ET.fromstring(raw_xml)
                entry_tag = "{http://www.w3.org/2005/Atom}entry"
                results = {}
                for entry in root.findall(entry_tag):
                    meta = scraper._parse_entry_meta(entry)
                    entry_id_raw = meta.get("id", "")
                    clean_id = entry_id_raw.split("/abs/")[-1] if "/abs/" in entry_id_raw else entry_id_raw
                    base_id = clean_id.split("v")[0]
                    results[clean_id] = meta
                    results[base_id] = meta
                return results
            except Exception as e:
                if attempt < retries:
                    backoff = attempt * 3.0
                    self.stdout.write(self.style.WARNING(f"      ⚠️ Transient error fetching arXiv batch (attempt {attempt}/{retries}): {e}. Retrying in {backoff}s..."))
                    time.sleep(backoff)
                else:
                    self.stdout.write(self.style.ERROR(f"      ❌ Failed to fetch arXiv batch after {retries} attempts: {e}"))
                    return {}

    def _fetch_openalex_entry(self, doi: str | None, title: str | None, retries: int = 2) -> dict | None:
        """
        Fetches metadata for a single paper from OpenAlex by DOI or title.
        """
        url = None
        if doi:
            clean_doi = doi.strip()
            if clean_doi.startswith("http"):
                url = f"https://api.openalex.org/works/{urllib.parse.quote(clean_doi, safe=':/')}"
            else:
                url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(clean_doi)}"
        elif title:
            url = f"https://api.openalex.org/works?search={urllib.parse.quote(title)}&per_page=1"

        if not url:
            return None

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'SchwarzResearchIntelligence/1.0 (mailto:research@schwarz-it.com)'}
        )

        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                if "results" in data:
                    results = data.get("results", [])
                    return results[0] if results else None
                return data
            except Exception as e:
                if attempt < retries:
                    time.sleep(attempt * 2.0)
                else:
                    return None
