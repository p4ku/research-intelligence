from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from research_intelligence.models import Star, WorkspaceMember
from ..serializers.stars import STAR_TARGETS, StarUpdateSerializer, StarsSerializer


class StarsView(APIView):
    """
    The authenticated user's starred papers and briefings (pipeline runs).
    Stars are personal: each user only ever reads or writes their own set.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _stars_payload(self, user, user_ws_ids=None):
        # Only targets the user can still see: a revoked membership hides its stars.
        if user_ws_ids is None:
            user_ws_ids = list(WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True))
        if not user_ws_ids:
            return {'papers': [], 'briefings': []}
        qs = Star.objects.filter(user=user).filter(
            Q(paper__workspace_id__in=user_ws_ids)
            | Q(pipeline_run__workspace_id__in=user_ws_ids)
        )

        papers = []
        briefings = []
        # Single-pass partition: iterate once over ordered stars (Meta.ordering: oldest star first)
        for paper_id, run_id in qs.values_list('paper_id', 'pipeline_run_id'):
            if paper_id:
                papers.append(paper_id)
            elif run_id:
                briefings.append(run_id)

        return StarsSerializer({'papers': papers, 'briefings': briefings}).data

    @extend_schema(
        responses={
            200: StarsSerializer,
            401: OpenApiResponse(description="Unauthorized - Token missing or expired"),
        },
        tags=['Stars & Curation']
    )
    def get(self, request, *args, **kwargs):
        return Response(self._stars_payload(request.user), status=status.HTTP_200_OK)

    @extend_schema(
        request=StarUpdateSerializer,
        responses={
            200: StarsSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Unauthorized"),
            404: OpenApiResponse(description="Paper or briefing not found in the user's workspaces"),
        },
        tags=['Stars & Curation']
    )
    def put(self, request, *args, **kwargs):
        serializer = StarUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        model, fk_field, kind, label = STAR_TARGETS[validated['kind']]
        target_id = validated['id']

        user_ws_ids = list(WorkspaceMember.objects.filter(user=request.user).values_list('workspace_id', flat=True))
        target_exists = bool(user_ws_ids) and model.objects.filter(id=target_id, workspace_id__in=user_ws_ids).exists()

        if not target_exists:
            return Response({"error": f"{label} not found."}, status=status.HTTP_404_NOT_FOUND)

        lookup = {'user': request.user, f'{fk_field}_id': target_id}
        if validated['starred']:
            # get_or_create wraps the insert in atomic() and re-gets on IntegrityError,
            # so concurrent PUTs for the same target are safe.
            Star.objects.get_or_create(**lookup, defaults={'kind': kind})
        else:
            Star.objects.filter(**lookup).delete()

        return Response(self._stars_payload(request.user, user_ws_ids=user_ws_ids), status=status.HTTP_200_OK)
