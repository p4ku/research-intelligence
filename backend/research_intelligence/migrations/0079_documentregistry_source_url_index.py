from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Adds a database index on DocumentRegistry.source_url.

    Context: Migration 0069 introduced the source_url field as a deduplication
    key for Google Patents (which lack a canonical PDF SHA-256 hash). However,
    it did not create an index on the field, causing every lookup via
    find_in_document_registry() to perform a full table scan on DocumentRegistry
    for patent papers. This migration adds the missing index.
    """

    dependencies = [
        ('research_intelligence', '0078_backfill_markdown_document_registry'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='documentregistry',
            index=models.Index(fields=['source_url'], name='research_in_source__url_idx'),
        ),
    ]
