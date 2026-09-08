import json
import uuid
from typing import Optional
from research_intelligence.models import Paper
from mcp_server.tools.workspaces.crud import check_workspace_access
from api.views.scorecard import build_paper_scorecard_data


def get_paper_scoreboard_logic(
    user,
    paper_id: str,
    pipeline_run_id: Optional[str] = None,
) -> str:
    """
    [MCP LOGIC: PAPER SCOREBOARD]
    Retrieves the complete, dynamic scoreboard/scorecard payload for a single paper,
    matching the frontend GET /api/papers/{id}/scorecard/ response contract.

    Returns:
      JSON string with:
      - workspace: Workspace summary (id, name, definitions count, scrapers count)
      - paper: Paper representation with resolved dimensions, composite signal_score & formula details,
               screening reasons, metadata, links
      - definitions: List of active extraction definitions with JSON Schemas, exit metrics & postprocessing code
      - extractions: Unflattened extracted JSON payload, confidence scores, HITL and validation flags
      - metric: Run-scoped PaperMetric row (screening status, decisions, scores)
      - narrative_report: Executive briefing Markdown report for the pipeline run
    """
    if not paper_id:
        return json.dumps({"status": "error", "error": "Parameter 'paper_id' is required."}, indent=2)

    try:
        p_uuid = uuid.UUID(str(paper_id).strip())
        paper = Paper.objects.select_related('workspace').get(id=p_uuid)
    except (ValueError, TypeError):
        return json.dumps({"status": "error", "error": f"Invalid UUID format for paper_id: '{paper_id}'."}, indent=2)
    except Paper.DoesNotExist:
        return json.dumps({"status": "error", "error": f"Paper with id '{paper_id}' does not exist."}, indent=2)

    workspace, membership, error = check_workspace_access(
        user, str(paper.workspace_id), required_roles=['admin', 'manager', 'researcher']
    )
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    data = build_paper_scorecard_data(paper, pipeline_run_id=pipeline_run_id)
    return json.dumps(data, indent=2, default=str)
