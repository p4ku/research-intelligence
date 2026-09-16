"""
Workspace Scoring Configuration and Worked Example Controller.

Encapsulates:
- GET /api/workspaces/{id}/scoring/
"""

from rest_framework import status
from rest_framework.response import Response

from research_intelligence.models import PaperMetric
from research_intelligence.services.scorecard_service import resolve_dimension_scale

__all__ = ['build_workspace_scoring_response']


def build_workspace_scoring_response(workspace) -> Response:
    """Build scoring formula configuration, active variables, calculated weights, and top paper calculation example."""
    active_defs = list(
        workspace.extraction_definitions.filter(is_active=True)
        .only('id', 'name')
        .order_by('created_at')
    )
    active_count = len(active_defs)
    default_weight = round(1000.0 / active_count) / 10.0 if active_count > 0 else 0

    variables = []
    weights = []

    for d in active_defs:
        key = d.name.lower().replace(' ', '_').replace('-', '_')
        max_val, is_trl = resolve_dimension_scale(d.name)
        def_id_str = str(d.id)

        variables.append({
            "key": key,
            "definition_id": def_id_str,
            "name": d.name,
            "max": max_val,
            "is_trl": is_trl or 'trl' in key,
        })
        weights.append({
            "key": key,
            "definition_id": def_id_str,
            "name": d.name,
            "weight": default_weight,
        })

    # Optimized fetch of top scored paper metric without loading heavy metrics_data
    top_pm = (
        PaperMetric.objects.filter(workspace=workspace, signal_score__isnull=False)
        .select_related('paper')
        .only(
            'id',
            'signal_score',
            'signal_score_details',
            'paper__id',
            'paper__title',
        )
        .order_by('-signal_score', '-created_at')
        .first()
    )

    example_obj = None
    pm_code_snippet = None

    if top_pm and top_pm.paper:
        details = top_pm.signal_score_details or {}
        pm_code_snippet = details.get("code_snippet")
        example_obj = {
            "paper_id": str(top_pm.paper.id),
            "title": top_pm.paper.title,
            "signal_score": top_pm.signal_score,
            "variables": details.get("variables", {}),
        }

    # Determine code and code_source
    if workspace.signal_score_code:
        code = workspace.signal_score_code
        code_source = "workspace"
    elif pm_code_snippet:
        code = pm_code_snippet
        code_source = "latest_metric"
    else:
        code = None
        code_source = "stub"

    return Response({
        "workspace_id": str(workspace.id),
        "code": code,
        "code_source": code_source,
        "variables": variables,
        "weights": weights,
        "weights_source": "stub",
        "example": example_obj,
    }, status=status.HTTP_200_OK)
