from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from research_intelligence.models import Workspace, WorkspaceMember, ExtractionDefinition
from ..serializers.workspaces import WorkspaceSerializer, ExtractionDefinitionSerializer
from ..serializers.pipeline_runs import StartPipelineRunSerializer


@extend_schema(
    tags=['Workspaces Management'],
    description="""
Manage SLR Workspace Projects, screening criteria, screening LLM engines, and default processing policies.

### Key Fields & Policies:
- **`reprocess_existing`** (boolean): Default workspace policy for pipeline runs. If `True`, pipeline runs re-evaluate and re-screen existing workspace papers even if no new papers are found from scrapers. This can be overridden per individual run via `configuration_override['reprocess_existing']` in API / MCP.
- **`skip_abstract_screening`** (boolean): If `True`, skips Abstract Screening and routes all candidate papers directly to multimodal Full-Text Screening.
- **`subscribers`**: Email recipients receiving automated execution reports and error alerts.
- **`workflow_schedules`**: Recurring (cron) and one-off execution schedules managed via `/api/schedules/`.
"""
)
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Workspace (Projects), dual-stage criteria, and processing policies.
    Scoped to workspaces the authenticated user is a member of.
    """
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'monthly_usd_limit']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return Workspace.objects.all().order_by('-created_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return Workspace.objects.filter(id__in=user_ws_ids).order_by('-created_at')

    def perform_create(self, serializer):
        workspace = serializer.save()
        # Automatically assign the creator as workspace admin
        WorkspaceMember.objects.get_or_create(
            workspace=workspace,
            user=self.request.user,
            defaults={'role': 'admin'}
        )

    def perform_update(self, serializer):
        workspace = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("Only workspace admins and managers can modify workspace settings.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance, user=user, role='admin'
            ).exists()
            if not has_access:
                raise PermissionDenied("Only workspace admins can delete this workspace.")

        # Purge workspace storage artifacts recursively
        try:
            from research_intelligence.admin_views.storage_browser import _recursive_delete_dir
            _recursive_delete_dir(f"workspaces/{instance.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not purge workspace storage directory: {e}")

        instance.delete()

    @extend_schema(
        tags=['Workspaces Management', 'Literature & Papers'],
        description="List papers ingested into this workspace, optionally filtered by pipeline_run or screening_status.",
    )
    @action(detail=True, methods=['get'], url_path='papers')
    def papers(self, request, pk=None):
        workspace = self.get_object()
        from ..views.papers import PaperViewSet
        from ..serializers.papers import PaperSerializer
        from rest_framework.response import Response

        paper_view = PaperViewSet()
        paper_view.request = request
        paper_view.format_kwarg = None

        # Scope query to this workspace
        q_params = request.query_params.copy()
        q_params['workspace'] = str(workspace.id)
        request._request.GET = q_params

        qs = paper_view.get_queryset().filter(workspace=workspace)
        page = paper_view.paginate_queryset(qs)
        if page is not None:
            serializer = PaperSerializer(page, many=True, context={'request': request, 'workspace': workspace})
            return paper_view.get_paginated_response(serializer.data)
        serializer = PaperSerializer(qs, many=True, context={'request': request, 'workspace': workspace})
        return Response(serializer.data)

    @extend_schema(
        tags=['Workspaces Management', 'Pipeline Runs & Components'],
        description="Trigger an autonomous pipeline run for this specific workspace with optional date range parameters.",
        request=StartPipelineRunSerializer,
        responses={
            201: OpenApiResponse(description="Autonomous pipeline run started for workspace"),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
        }
    )
    @action(detail=True, methods=['post'], url_path='run-pipeline')
    def run_pipeline(self, request, pk=None):
        import json
        from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic

        workspace = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['workspace_id'] = str(workspace.id)

        serializer = StartPipelineRunSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        valid_data = serializer.validated_data
        n_last_days = valid_data.get('n_last_days')
        res_json = start_pipeline_run_logic(
            user=request.user,
            workspace_id=str(workspace.id),
            name=valid_data.get('name'),
            limit=valid_data.get('limit'),
            query_prefix=valid_data.get('query_prefix'),
            skip_abstract_screening=valid_data.get('skip_abstract_screening'),
            notification_email=valid_data.get('notification_email'),
            reprocess_existing=valid_data.get('reprocess_existing'),
            autonomous=valid_data.get('autonomous', True),
            start_date=valid_data.get('start_date'),
            end_date=valid_data.get('end_date'),
            n_last_days=n_last_days
        )
        try:
            res_data = json.loads(res_json)
        except Exception:
            res_data = {"raw_response": res_json}

        if isinstance(res_data, dict) and res_data.get("status") == "error":
            err_msg = res_data.get("error", "Error starting pipeline run")
            if "denied" in err_msg.lower() or "permissions" in err_msg.lower():
                return Response(res_data, status=status.HTTP_403_FORBIDDEN)
            return Response(res_data, status=status.HTTP_400_BAD_REQUEST)

        return Response(res_data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Extraction Definitions'])
class ExtractionDefinitionViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for dynamic Extraction Definitions within a workspace.
    """
    serializer_class = ExtractionDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering_fields = ['created_at', 'name', 'version', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return ExtractionDefinition.objects.all().order_by('-created_at')
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
        return ExtractionDefinition.objects.filter(workspace_id__in=user_ws_ids).order_by('-created_at')

    def perform_create(self, serializer):
        workspace = serializer.validated_data.get('workspace')
        if not workspace:
            raise PermissionDenied("Workspace is required.")
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=obj.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            has_access = WorkspaceMember.objects.filter(
                workspace=instance.workspace, user=user, role__in=['admin', 'manager']
            ).exists()
            if not has_access:
                raise PermissionDenied("You do not have permission to manage extraction definitions in this workspace.")
        instance.delete()

