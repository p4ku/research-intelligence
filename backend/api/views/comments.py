import uuid
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from api.pagination import StandardResultsSetPagination
from api.serializers.comments import PaperCommentSerializer, PaperCommentReactionSerializer
from research_intelligence.models import (
    Paper,
    PipelineRun,
    PaperComment,
    PaperCommentReaction,
    WorkspaceMember,
)


@extend_schema(
    tags=['Paper Comments & Collaboration'],
    parameters=[
        OpenApiParameter(name='paper', type=str, location=OpenApiParameter.QUERY, description='Filter comments by Paper UUID'),
        OpenApiParameter(name='pipeline_run', type=str, location=OpenApiParameter.QUERY, description='Filter comments by PipelineRun UUID (includes cross-run comments)'),
        OpenApiParameter(name='include_deleted', type=bool, location=OpenApiParameter.QUERY, description='Set true to include soft-deleted comments (default false)'),
    ]
)
class PaperCommentViewSet(viewsets.ModelViewSet):
    """
    CRUD API for collaborative research comments and discussion messages per paper.
    
    Security & Multi-Tenant Isolation:
    - Reading: Strictly scoped to workspaces the authenticated user belongs to. Non-members receive 404 (zero data leakage).
    - Creation: Allowed only if the user is a verified member of the paper's workspace.
    - Modification & Deletion: Allowed for the comment author (owner) OR workspace admins / managers, preventing unauthorized edits while enabling team moderation.
    """
    queryset = PaperComment.objects.none()
    serializer_class = PaperCommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    ordering = ['created_at', 'id']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PaperComment.objects.none()

        if user.is_superuser:
            qs = PaperComment.objects.all()
        else:
            user_ws_ids = set(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
            if not user_ws_ids:
                return PaperComment.objects.none()
            qs = PaperComment.objects.filter(workspace_id__in=user_ws_ids)

        # Performance optimization: prefetch relations in a single SQL query
        qs = qs.select_related(
            'user', 'resolved_by', 'workspace', 'paper', 'pipeline_run'
        ).prefetch_related(
            'reactions__user', 'mentions'
        )

        # Filter by paper
        paper_param = (
            self.request.query_params.get('paper')
            or self.request.query_params.get('paper_id')
        )
        if paper_param:
            try:
                paper_uuid = uuid.UUID(str(paper_param))
                qs = qs.filter(paper_id=paper_uuid)
            except (ValueError, TypeError):
                return qs.none()

        # Filter by pipeline_run
        pr_param = (
            self.request.query_params.get('pipeline_run')
            or self.request.query_params.get('pipeline_run_id')
            or self.request.query_params.get('run_id')
        )
        if pr_param and str(pr_param).lower() not in ('undefined', 'null', ''):
            try:
                pr_uuid = uuid.UUID(str(pr_param))
                # Include comments specific to this run AND cross-run comments (pipeline_run is null)
                qs = qs.filter(Q(pipeline_run_id=pr_uuid) | Q(pipeline_run__isnull=True))
            except (ValueError, TypeError):
                pass

        # Exclude soft-deleted comments unless requested or during destroy/hard-delete operations
        include_deleted = (
            self.request.query_params.get('include_deleted', 'false').lower() in ('true', '1')
            or self.request.query_params.get('hard', 'false').lower() in ('true', '1')
            or self.action == 'destroy'
        )
        if not include_deleted:
            qs = qs.filter(is_deleted=False)

        return qs.order_by('created_at', 'id')

    def _check_workspace_membership(self, workspace_id) -> tuple[bool, str]:
        """
        Returns (has_access, role). Superuser is treated as 'admin'.
        """
        user = self.request.user
        if user.is_superuser:
            return True, 'admin'
        membership = WorkspaceMember.objects.filter(workspace_id=workspace_id, user=user).first()
        if membership:
            return True, membership.role
        return False, ''

    def _check_modify_permission(self, comment: PaperComment):
        """
        Enforces that either:
        - The user is the comment author (owner), OR
        - The user is an admin or manager in the comment's workspace, OR
        - The user is a superuser.
        """
        user = self.request.user
        if user.is_superuser:
            return True

        has_access, role = self._check_workspace_membership(comment.workspace_id)
        if not has_access:
            raise PermissionDenied("You are not a member of this workspace.")

        is_owner = (comment.user_id == user.id)
        is_elevated = (role in ['admin', 'manager'])

        if not (is_owner or is_elevated):
            raise PermissionDenied(
                "You do not have permission to modify this comment. Only the comment author or workspace admins/managers can edit or delete."
            )
        return True

    def perform_create(self, serializer):
        user = self.request.user
        paper = serializer.validated_data.get('paper')
        if not paper:
            # Fallback to query param or request data if paper passed as string UUID
            paper_id = (
                self.request.data.get('paper')
                or self.request.data.get('paper_id')
                or self.request.query_params.get('paper')
                or self.request.query_params.get('paper_id')
            )
            if paper_id:
                try:
                    paper = Paper.objects.get(id=uuid.UUID(str(paper_id)))
                except (Paper.DoesNotExist, ValueError):
                    raise ValidationError({'paper': 'Valid target paper is required.'})
            else:
                raise ValidationError({'paper': 'Target paper is required.'})

        # 1. Verify user belongs to paper's workspace
        has_access, role = self._check_workspace_membership(paper.workspace_id)
        if not has_access:
            raise PermissionDenied("You must be a member of the paper's workspace to post comments.")

        # 2. Pipeline run workspace verification
        pipeline_run = serializer.validated_data.get('pipeline_run')
        if pipeline_run and pipeline_run.workspace_id != paper.workspace_id:
            raise ValidationError({'pipeline_run': 'PipelineRun must belong to the same workspace as the paper.'})

        # 3. Pinning permission: only admins/managers can pin
        is_pinned = serializer.validated_data.get('is_pinned', False)
        if is_pinned and role not in ['admin', 'manager'] and not user.is_superuser:
            is_pinned = False

        serializer.save(
            user=user,
            paper=paper,
            workspace=paper.workspace,
            is_pinned=is_pinned
        )

    def perform_update(self, serializer):
        comment = self.get_object()
        self._check_modify_permission(comment)

        # Disallow moving comments between papers or workspaces
        if 'paper' in serializer.validated_data and serializer.validated_data['paper'] != comment.paper:
            raise ValidationError({'paper': 'Comments cannot be moved to another paper.'})

        new_content = serializer.validated_data.get('content')
        is_edited = comment.is_edited
        if new_content is not None and new_content != comment.content:
            is_edited = True

        serializer.save(is_edited=is_edited)

    def perform_destroy(self, instance):
        self._check_modify_permission(instance)
        hard_delete = self.request.query_params.get('hard', 'false').lower() in ('true', '1')
        if hard_delete:
            instance.delete()
        else:
            # Soft delete preserving thread discussion integrity
            instance.soft_delete()

    @extend_schema(
        description="Mark a comment thread as resolved or unresolve it.",
        responses={200: PaperCommentSerializer}
    )
    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        comment = self.get_object()
        has_access, _ = self._check_workspace_membership(comment.workspace_id)
        if not has_access:
            raise PermissionDenied("You are not a member of this workspace.")

        action_type = request.data.get('action', 'toggle')
        if action_type == 'unresolve' or (action_type == 'toggle' and comment.is_resolved):
            comment.unresolve()
        else:
            comment.resolve(resolving_user=request.user)

        serializer = self.get_serializer(comment)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        description="Add or toggle an emoji reaction (thumbs_up, bulb, rocket, etc.) on a comment.",
        responses={200: OpenApiResponse(description="Updated reactions array")}
    )
    @action(detail=True, methods=['post'], url_path='reactions')
    def reactions(self, request, pk=None):
        comment = self.get_object()
        has_access, _ = self._check_workspace_membership(comment.workspace_id)
        if not has_access:
            raise PermissionDenied("You are not a member of this workspace.")

        reaction_type = (request.data.get('reaction_type') or request.data.get('type') or '').strip()
        allowed_types = [c[0] for c in PaperCommentReaction.REACTION_CHOICES]
        if reaction_type not in allowed_types:
            return Response(
                {'error': f"Invalid reaction_type. Allowed: {', '.join(allowed_types)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        existing = PaperCommentReaction.objects.filter(
            comment=comment, user=request.user, reaction_type=reaction_type
        ).first()

        if existing:
            # Toggle off
            existing.delete()
            action_taken = 'removed'
        else:
            # Toggle on
            PaperCommentReaction.objects.create(
                comment=comment, user=request.user, reaction_type=reaction_type
            )
            action_taken = 'added'

        if hasattr(comment, '_prefetched_objects_cache'):
            comment._prefetched_objects_cache.clear()

        serializer = self.get_serializer(comment)
        return Response({
            'action': action_taken,
            'reactions': serializer.data.get('reactions', [])
        }, status=status.HTTP_200_OK)
