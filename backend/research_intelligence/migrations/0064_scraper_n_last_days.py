from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('research_intelligence', '0063_documentregistry_meta_paper_meta'),
    ]

    operations = [
        migrations.AddField(
            model_name='scraper',
            name='n_last_days',
            field=models.IntegerField(default=7, help_text='Default days lookback window when date range is omitted'),
        ),
    ]
