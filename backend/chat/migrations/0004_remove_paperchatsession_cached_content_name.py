from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_paperchatmessage_thinking_process'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='paperchatsession',
            name='cached_content_name',
        ),
    ]
