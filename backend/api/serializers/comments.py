from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from research_intelligence.models import (
    Paper,
    PipelineRun,
    Extraction,
    PaperComment,
    PaperCommentReaction,
)

User = get_user_model()


class PaperCommentUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'name']

    def get_name(self, obj) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username


class PaperCommentReactionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PaperCommentReaction
        fields = ['id', 'user_id', 'username', 'reaction_type', 'created_at']


class PaperCommentSerializer(serializers.ModelSerializer):
    user = PaperCommentUserSerializer(read_only=True)
    resolved_by = PaperCommentUserSerializer(read_only=True)
    reactions = serializers.SerializerMethodField()

    # Writable relation fields for creation / updates
    paper = serializers.PrimaryKeyRelatedField(
        queryset=Paper.objects.all(),
        required=False,
        write_only=True
    )
    pipeline_run = serializers.PrimaryKeyRelatedField(
        queryset=PipelineRun.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=PaperComment.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    extraction = serializers.PrimaryKeyRelatedField(
        queryset=Extraction.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )

    class Meta:
        model = PaperComment
        fields = [
            'id',
            'workspace_id',
            'paper',
            'paper_id',
            'pipeline_run',
            'pipeline_run_id',
            'user',
            'parent',
            'parent_id',
            'content',
            'comment_type',
            'status',
            'is_pinned',
            'is_resolved',
            'resolved_by',
            'resolved_at',
            'is_edited',
            'is_deleted',
            'reactions',
            'anchor_text',
            'anchor_context',
            'extraction',
            'extraction_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'workspace_id', 'paper_id', 'pipeline_run_id', 'parent_id', 'extraction_id', 'user', 'created_at', 'updated_at']

    def get_reactions(self, obj) -> list[dict]:
        """
        Groups reactions by reaction_type with counts, participant usernames,
        and whether the requesting user has reacted.
        """
        req_user = None
        if 'request' in self.context and hasattr(self.context['request'], 'user'):
            req_user = self.context['request'].user

        aggregated = {}
        for r in obj.reactions.all():
            rtype = r.reaction_type
            if rtype not in aggregated:
                aggregated[rtype] = {
                    'reaction_type': rtype,
                    'count': 0,
                    'users': [],
                    'has_reacted': False,
                }
            aggregated[rtype]['count'] += 1
            username = getattr(r.user, 'username', str(r.user_id))
            aggregated[rtype]['users'].append(username)
            if req_user and req_user.is_authenticated and r.user_id == req_user.id:
                aggregated[rtype]['has_reacted'] = True

        return list(aggregated.values())


def get_default_placeholder_messages(paper, target_pr_id=None) -> list[dict]:
    """
    Returns structured developer placeholder messages (chronological order)
    when no comments exist yet in the database.
    """
    pr_str = str(target_pr_id) if target_pr_id else None
    ws_str = str(paper.workspace_id)

    return [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": ws_str,
            "paper_id": str(paper.id),
            "pipeline_run_id": pr_str,
            "user": {
                "id": 101,
                "username": "dr.schwarz",
                "email": "dr.schwarz@schwarz.internal",
                "name": "Dr. Sarah Schwarz"
            },
            "parent_id": None,
            "content": "Notice the benchmark comparison on page 4 — how does their rotary embedding scaling compare to our internal baseline?",
            "comment_type": "question",
            "status": "active",
            "is_pinned": True,
            "is_resolved": False,
            "resolved_by": None,
            "resolved_at": None,
            "is_edited": False,
            "is_deleted": False,
            "reactions": [
                {
                    "reaction_type": "bulb",
                    "count": 3,
                    "users": ["m.kovac", "j.doe", "a.turing"],
                    "has_reacted": False
                },
                {
                    "reaction_type": "thumbs_up",
                    "count": 2,
                    "users": ["m.kovac", "j.doe"],
                    "has_reacted": True
                }
            ],
            "anchor_text": "We evaluate rotary positional embeddings across all 48 attention heads against standard sinusoidal encodings.",
            "anchor_context": {"page": 4, "section": "Experiments"},
            "extraction_id": None,
            "created_at": "2026-09-19T09:30:00Z",
            "updated_at": "2026-09-19T09:30:00Z"
        },
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "workspace_id": ws_str,
            "paper_id": str(paper.id),
            "pipeline_run_id": pr_str,
            "user": {
                "id": 102,
                "username": "m.kovac",
                "email": "m.kovac@schwarz.internal",
                "name": "Martin Kovac"
            },
            "parent_id": "00000000-0000-0000-0000-000000000001",
            "content": "Rechecked table 3: throughput improves by ~18% with zero degradation on retrieval accuracy. Definitely worth adopting in the next pipeline iteration.",
            "comment_type": "finding",
            "status": "active",
            "is_pinned": False,
            "is_resolved": False,
            "resolved_by": None,
            "resolved_at": None,
            "is_edited": False,
            "is_deleted": False,
            "reactions": [
                {
                    "reaction_type": "rocket",
                    "count": 4,
                    "users": ["dr.schwarz", "j.doe", "a.turing", "e.bohr"],
                    "has_reacted": False
                }
            ],
            "anchor_text": None,
            "anchor_context": {},
            "extraction_id": None,
            "created_at": "2026-09-19T10:15:00Z",
            "updated_at": "2026-09-19T10:15:00Z"
        }
    ]


def get_paper_messages_payload(paper, target_pr_id=None, request=None) -> list[dict]:
    """
    Fetches real PaperComment objects for the given paper within its workspace,
    scoped either to the run or cross-run (pipeline_run is None),
    strictly sorted chronological (oldest on top, newest at bottom).
    
    If no comments exist in the database, returns developer placeholder messages
    illustrating the complete collaborative chat message structure.
    """
    if not paper or not paper.id:
        return []

    # Filter comments for this paper:
    # 1. Matches paper and workspace
    # 2. pipeline_run is None (cross-run comments) OR pipeline_run == target_pr_id
    run_filter = Q(pipeline_run__isnull=True)
    if target_pr_id and str(target_pr_id).lower() not in ('undefined', 'null', ''):
        run_filter |= Q(pipeline_run_id=target_pr_id)

    comments_qs = (
        PaperComment.objects.filter(paper=paper, workspace=paper.workspace)
        .filter(run_filter)
        .select_related('user', 'resolved_by')
        .prefetch_related('reactions__user')
        .order_by('created_at', 'id')  # oldest on top, newest at bottom
    )

    comments = list(comments_qs)
    if not comments:
        return get_default_placeholder_messages(paper, target_pr_id=target_pr_id)

    serializer = PaperCommentSerializer(comments, many=True, context={'request': request})
    return serializer.data
