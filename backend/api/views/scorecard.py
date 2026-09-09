"""
Paper & Workspace Scorecard API Views and Controllers.

Exposes endpoints and response builders for:
- GET /api/papers/{id}/scorecard/
- GET /api/workspaces/{id}/scorecard/

The heavy extraction parsing, metric classification, and payload assembly
are encapsulated in `research_intelligence.services.scorecard_extractors`
and `research_intelligence.services.scorecard_service`.
"""

from rest_framework import status
from rest_framework.response import Response

from research_intelligence.models import Paper
from research_intelligence.services.scorecard_extractors import (
    build_metric_entry,
    extract_metrics_for_extraction,
    extract_rich_dimension_details,
    extract_risk_and_affiliation,
    format_metric_label,
    humanise_field_label,
    is_risk_dimension,
    resolve_field_val,
)
from research_intelligence.services.scorecard_service import (
    build_paper_scorecard_data,
    build_single_scored_paper,
    build_workspace_scorecard_data,
    format_definitions_metadata,
)

__all__ = [
    'build_paper_scorecard_response',
    'build_workspace_scorecard_response',
    'build_paper_scorecard_data',
    'build_workspace_scorecard_data',
    'build_single_scored_paper',
    'format_definitions_metadata',
    'extract_metrics_for_extraction',
    'extract_rich_dimension_details',
    'extract_risk_and_affiliation',
    'is_risk_dimension',
    'build_metric_entry',
    'format_metric_label',
    'humanise_field_label',
    'resolve_field_val',
]


def build_paper_scorecard_response(paper: Paper, request) -> Response:
    """HTTP view controller for GET /api/papers/{id}/scorecard/."""
    try:
        pipeline_run_param = (
            request.query_params.get('pipeline_run')
            or request.query_params.get('pipeline_run_id')
            or request.query_params.get('run_id')
        )
        data = build_paper_scorecard_data(paper, pipeline_run_id=pipeline_run_param, request=request)
        return Response(data, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response(
            {
                'error': 'Failed to build paper scorecard',
                'detail': str(exc),
                'paper_id': str(paper.id),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def build_workspace_scorecard_response(workspace, request) -> Response:
    """HTTP view controller for GET /api/workspaces/{id}/scorecard/."""
    try:
        pipeline_run_param = (
            request.query_params.get('run_id')
            or request.query_params.get('pipeline_run')
            or request.query_params.get('pipeline_run_id')
        )
        data = build_workspace_scorecard_data(workspace, pipeline_run_id=pipeline_run_param, request=request)
        return Response(data, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response(
            {
                'error': 'Failed to build workspace scorecard',
                'detail': str(exc),
                'workspace_id': str(workspace.id),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
