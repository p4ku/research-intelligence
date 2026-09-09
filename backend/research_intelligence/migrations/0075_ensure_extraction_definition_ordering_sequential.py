from django.db import migrations


def ensure_sequential_ordering(apps, schema_editor):
    ExtractionDefinition = apps.get_model('research_intelligence', 'ExtractionDefinition')
    Workspace = apps.get_model('research_intelligence', 'Workspace')

    for ws in Workspace.objects.all():
        defs = list(
            ExtractionDefinition.objects.filter(workspace=ws)
            .order_by('order', 'created_at', 'id')
        )
        for idx, ed in enumerate(defs, start=1):
            if ed.order != idx:
                ed.order = idx
                ed.save(update_fields=['order'])


class Migration(migrations.Migration):

    dependencies = [
        ('research_intelligence', '0074_extractiondefinition_order'),
    ]

    operations = [
        migrations.RunPython(
            ensure_sequential_ordering,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
