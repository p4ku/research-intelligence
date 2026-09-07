from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from research_intelligence.models import Paper, PipelineRun, Star
from ..serializers.stars import STAR_TARGETS, StarUpdateSerializer, StarsSerializer


class StarsView(APIView):
    """
    The authenticated user's starred papers and briefings (pipeline runs).
    Stars are personal: each user only ever reads or writes their own set.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _stars_payload(self, user):
        qs = Star.objects.filter(user=user)
        if not getattr(user, 'is_superuser', False):
            # Only targets the user can still see: a revoked membership hides its stars.
            qs = qs.filter(
                Q(paper__in=Paper.objects.for_user(user))
                | Q(pipeline_run__in=PipelineRun.objects.for_user(user))
            )
        rows = qs.values_list('paper_id', 'pipeline_run_id')  # Meta.ordering: oldest star first
        papers = [paper_id for paper_id, _ in rows if paper_id]
        briefings = [run_id for _, run_id in rows if run_id]
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

        if not model.objects.for_user(request.user).filter(id=target_id).exists():
            return Response({"error": f"{label} not found."}, status=status.HTTP_404_NOT_FOUND)

        lookup = {'user': request.user, f'{fk_field}_id': target_id}
        if validated['starred']:
            # get_or_create wraps the insert in atomic() and re-gets on IntegrityError,
            # so concurrent PUTs for the same target are safe.
            Star.objects.get_or_create(**lookup, defaults={'kind': kind})
        else:
            Star.objects.filter(**lookup).delete()

        return Response(self._stars_payload(request.user), status=status.HTTP_200_OK)
