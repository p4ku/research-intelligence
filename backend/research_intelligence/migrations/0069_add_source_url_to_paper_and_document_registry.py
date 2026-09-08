from django.db import migrations, models


def backfill_source_urls(apps, schema_editor):
    """
    Backfills source_url on existing Paper and DocumentRegistry records
    from DOI, arXiv ID, or raw provider metadata.
    """
    Paper = apps.get_model('research_intelligence', 'Paper')
    DocumentRegistry = apps.get_model('research_intelligence', 'DocumentRegistry')

    # 1. Backfill Paper records
    for p in Paper.objects.filter(source_url__isnull=True).iterator(chunk_size=500):
        url = None
        if p.doi:
            clean_doi = str(p.doi).strip()
            for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
                if clean_doi.lower().startswith(prefix):
                    clean_doi = clean_doi[len(prefix):]
            if clean_doi:
                url = f"https://doi.org/{clean_doi}"
        elif p.arxiv_id:
            clean_arxiv = str(p.arxiv_id).strip()
            if clean_arxiv.lower().startswith("arxiv:"):
                clean_arxiv = clean_arxiv[6:]
            if clean_arxiv:
                url = f"https://arxiv.org/abs/{clean_arxiv}"
        elif p.meta and isinstance(p.meta, dict):
            openalex_id = p.meta.get("id")
            if openalex_id and str(openalex_id).startswith("http"):
                url = str(openalex_id)
            else:
                prim_loc = p.meta.get("primary_location")
                if isinstance(prim_loc, dict) and prim_loc.get("landing_page_url"):
                    url = prim_loc.get("landing_page_url")
                else:
                    other_url = p.meta.get("landing_page_url") or p.meta.get("other_url") or p.meta.get("url")
                    if other_url and str(other_url).startswith("http"):
                        url = str(other_url)
        elif p.source_database == "openalex" and p.hash_id:
            raw_hash = str(p.hash_id).strip()
            if raw_hash.startswith("W") and raw_hash[1:].isdigit():
                url = f"https://openalex.org/{raw_hash}"

        if url:
            p.source_url = url[:1024]
            p.save(update_fields=['source_url'])

    # 2. Backfill DocumentRegistry records
    for doc in DocumentRegistry.objects.filter(source_url__isnull=True).iterator(chunk_size=500):
        url = None
        if doc.doi:
            clean_doi = str(doc.doi).strip()
            for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
                if clean_doi.lower().startswith(prefix):
                    clean_doi = clean_doi[len(prefix):]
            if clean_doi:
                url = f"https://doi.org/{clean_doi}"
        elif doc.arxiv_id:
            clean_arxiv = str(doc.arxiv_id).strip()
            if clean_arxiv.lower().startswith("arxiv:"):
                clean_arxiv = clean_arxiv[6:]
            if clean_arxiv:
                url = f"https://arxiv.org/abs/{clean_arxiv}"
        elif doc.meta and isinstance(doc.meta, dict):
            openalex_id = doc.meta.get("id")
            if openalex_id and str(openalex_id).startswith("http"):
                url = str(openalex_id)
            else:
                prim_loc = doc.meta.get("primary_location")
                if isinstance(prim_loc, dict) and prim_loc.get("landing_page_url"):
                    url = prim_loc.get("landing_page_url")
                else:
                    other_url = doc.meta.get("landing_page_url") or doc.meta.get("other_url") or doc.meta.get("url")
                    if other_url and str(other_url).startswith("http"):
                        url = str(other_url)

        if url:
            doc.source_url = url[:1024]
            doc.save(update_fields=['source_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('research_intelligence', '0068_workspace_narrative_report_prompt_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentregistry',
            name='source_url',
            field=models.URLField(blank=True, help_text='Original public web URL to article or landing page', max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='paper',
            name='source_url',
            field=models.URLField(blank=True, help_text='Original public web URL to article landing page or repository', max_length=1024, null=True),
        ),
        migrations.RunPython(backfill_source_urls, migrations.RunPython.noop),
    ]
