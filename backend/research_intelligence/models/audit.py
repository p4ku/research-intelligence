import uuid
import logging
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class UserActivityLog(models.Model):
    """
    Immutable audit log capturing user actions across FastMCP tools and REST API endpoints.
    Preserves historical traceability even after User or Workspace deletion via denormalized fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Foreign keys (SET_NULL on deletion to maintain audit record)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    workspace = models.ForeignKey('Workspace', on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    
    # Denormalized historical strings (Preserved even if user/workspace row is deleted!)
    user_username = models.CharField(max_length=255, blank=True, help_text="Historical username at action execution")
    user_email = models.CharField(max_length=255, blank=True, help_text="Historical email at action execution")
    workspace_name = models.CharField(max_length=255, blank=True, help_text="Historical workspace name at action execution")
    
    # Action Metadata
    interface = models.CharField(max_length=50, help_text="'mcp' or 'rest_api'")
    action_name = models.CharField(max_length=255, help_text="e.g. 'start_research_agent', 'POST /api/agents/'")
    status = models.CharField(max_length=50, default="success", help_text="'success', 'failed', 'unauthorized'")
    
    # Payloads & Execution Trace
    input_params = models.JSONField(blank=True, null=True, help_text="Parameters / request body sent by user")
    output_summary = models.JSONField(blank=True, null=True, help_text="Response payload or summary returned")
    error_message = models.TextField(blank=True, null=True, help_text="Error traceback or failure reason if status != success")
    execution_time_ms = models.FloatField(default=0.0, help_text="Duration of operation in milliseconds")
    
    # Client Context
    api_key_id = models.CharField(max_length=255, blank=True, null=True, help_text="MCP API Key ID used")
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True, null=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['workspace', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['interface', 'action_name']),
            models.Index(fields=['status']),
        ]

    @classmethod
    def log_action(
        cls,
        user=None,
        workspace=None,
        interface: str = "mcp",
        action_name: str = "",
        status: str = "success",
        input_params: dict = None,
        output_summary: dict = None,
        error_message: str = None,
        execution_time_ms: float = 0.0,
        api_key_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Helper factory creating UserActivityLog entries with automatic workspace resolution and denormalization."""
        from .workspace import Workspace, Scraper
        from .pipeline import PipelineRun, ResearchAgentProcess, ComponentRun
        from .paper import Paper
        from .extraction import ExtractionDefinition, Extraction

        # 1. Resolve Workspace if passed directly as Workspace instance or UUID/str
        ws_obj = None
        if isinstance(workspace, Workspace):
            ws_obj = workspace
        elif isinstance(workspace, (str, uuid.UUID)):
            try:
                ws_obj = Workspace.objects.filter(id=workspace).first()
            except Exception:
                ws_obj = None

        # 2. Intelligent workspace resolution from input_params / kwargs
        if not ws_obj and isinstance(input_params, dict):
            try:
                ws_val = input_params.get('workspace_id') or input_params.get('workspace')
                if ws_val:
                    if isinstance(ws_val, Workspace):
                        ws_obj = ws_val
                    else:
                        ws_obj = Workspace.objects.filter(id=ws_val).first()

                if not ws_obj and input_params.get('pipeline_run_id'):
                    pr = PipelineRun.objects.filter(id=input_params['pipeline_run_id']).select_related('workspace').first()
                    if pr:
                        ws_obj = pr.workspace

                if not ws_obj and (input_params.get('process_id') or input_params.get('agent_process_id')):
                    p_id = input_params.get('process_id') or input_params.get('agent_process_id')
                    proc = ResearchAgentProcess.objects.filter(id=p_id).select_related('workspace').first()
                    if proc:
                        ws_obj = proc.workspace

                if not ws_obj and input_params.get('paper_id'):
                    paper = Paper.objects.filter(id=input_params['paper_id']).select_related('workspace').first()
                    if paper:
                        ws_obj = paper.workspace

                if not ws_obj and input_params.get('scraper_id'):
                    scraper = Scraper.objects.filter(id=input_params['scraper_id']).select_related('workspace').first()
                    if scraper:
                        ws_obj = scraper.workspace

                if not ws_obj and input_params.get('definition_id'):
                    ext_def = ExtractionDefinition.objects.filter(id=input_params['definition_id']).select_related('workspace').first()
                    if ext_def:
                        ws_obj = ext_def.workspace

                if not ws_obj and input_params.get('extraction_id'):
                    ext = Extraction.objects.filter(id=input_params['extraction_id']).select_related('workspace').first()
                    if ext:
                        ws_obj = ext.workspace

                if not ws_obj and input_params.get('component_run_id'):
                    cr = ComponentRun.objects.filter(id=input_params['component_run_id']).select_related('pipeline_run__workspace').first()
                    if cr and cr.pipeline_run:
                        ws_obj = cr.pipeline_run.workspace
            except Exception:
                pass

        # 3. Intelligent workspace resolution from output_summary (e.g. create_workspace returns workspace_id)
        if not ws_obj and isinstance(output_summary, dict):
            try:
                out_ws = output_summary.get('workspace_id') or output_summary.get('workspace')
                if not out_ws and action_name in ('create_workspace', 'POST /api/workspaces/'):
                    out_ws = output_summary.get('id')
                if out_ws:
                    ws_obj = Workspace.objects.filter(id=out_ws).first()
            except Exception:
                pass

        # 4. Intelligent workspace resolution from REST API URL path (e.g. /api/workspaces/<uuid>/)
        if not ws_obj and action_name:
            try:
                import re
                uuid_match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', action_name)
                if uuid_match:
                    matched_id = uuid_match.group(0)
                    if '/workspaces/' in action_name:
                        ws_obj = Workspace.objects.filter(id=matched_id).first()
                    elif '/agents/' in action_name:
                        proc = ResearchAgentProcess.objects.filter(id=matched_id).select_related('workspace').first()
                        if proc:
                            ws_obj = proc.workspace
                    elif '/pipeline-runs/' in action_name:
                        pr = PipelineRun.objects.filter(id=matched_id).select_related('workspace').first()
                        if pr:
                            ws_obj = pr.workspace
                    elif '/extractions/' in action_name:
                        ext = Extraction.objects.filter(id=matched_id).select_related('workspace').first()
                        if ext:
                            ws_obj = ext.workspace
            except Exception:
                pass

        username = getattr(user, 'username', '') if user else ''
        email = getattr(user, 'email', '') if user else ''
        ws_name = getattr(ws_obj, 'name', '') if ws_obj else ''

        logger.info(
            f"📝 [USER ACTIVITY LOG] [{interface.upper()}] {action_name} | "
            f"User: '{username or 'Anonymous'}' ({email or 'N/A'}) | "
            f"Workspace: '{ws_name or 'N/A'}' | "
            f"Status: {status.upper()} ({execution_time_ms:.1f}ms)"
        )

        return cls.objects.create(
            user=user,
            workspace=ws_obj,
            user_username=username,
            user_email=email,
            workspace_name=ws_name,
            interface=interface,
            action_name=action_name,
            status=status,
            input_params=input_params,
            output_summary=output_summary,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            api_key_id=api_key_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

    def __str__(self):
        user_str = self.user_username or (str(self.user) if self.user else "Anonymous")
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_str} executed {self.action_name} ({self.status})"
