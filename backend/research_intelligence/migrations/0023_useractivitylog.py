import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('research_intelligence', '0022_remove_workspace_acceptance_criteria_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserActivityLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('user_username', models.CharField(blank=True, help_text='Historical username at action execution', max_length=255)),
                ('user_email', models.CharField(blank=True, help_text='Historical email at action execution', max_length=255)),
                ('workspace_name', models.CharField(blank=True, help_text='Historical workspace name at action execution', max_length=255)),
                ('interface', models.CharField(help_text="'mcp' or 'rest_api'", max_length=50)),
                ('action_name', models.CharField(help_text="e.g. 'start_research_agent', 'POST /api/agents/'", max_length=255)),
                ('status', models.CharField(default='success', help_text="'success', 'failed', 'unauthorized'", max_length=50)),
                ('input_params', models.JSONField(blank=True, help_text='Parameters / request body sent by user', null=True)),
                ('output_summary', models.JSONField(blank=True, help_text='Response payload or summary returned', null=True)),
                ('error_message', models.TextField(blank=True, help_text='Error traceback or failure reason if status != success', null=True)),
                ('execution_time_ms', models.FloatField(default=0.0, help_text='Duration of operation in milliseconds')),
                ('api_key_id', models.CharField(blank=True, help_text='MCP API Key ID used', max_length=255, null=True)),
                ('ip_address', models.CharField(blank=True, max_length=100, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=512, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL)),
                ('workspace', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to='research_intelligence.workspace')),
            ],
            options={
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['-timestamp'], name='research_in_timesta_04a8ad_idx'),
                    models.Index(fields=['interface', 'action_name'], name='research_in_interfa_b3c3bf_idx'),
                    models.Index(fields=['status'], name='research_in_status_7cf597_idx'),
                ],
            },
        ),
    ]
