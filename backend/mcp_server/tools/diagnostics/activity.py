import json
from research_intelligence.models import UserActivityLog
from research_intelligence.services import check_workspace_access


def list_user_activity_logs_logic(
    user,
    workspace_id: str = None,
    interface: str = None,
    status: str = None,
    limit: int = 50
) -> str:
    """
    Retrieve user & API activity log history for auditing and operational traceability.
    """
    queryset = UserActivityLog.objects.all()

    if workspace_id:
        workspace, membership, error = check_workspace_access(user, workspace_id, required_roles=['admin', 'manager', 'researcher'])
        if error:
            return json.dumps({"status": "error", "error": error}, indent=2)
        queryset = queryset.filter(workspace=workspace)

    if interface:
        queryset = queryset.filter(interface=interface)

    if status:
        queryset = queryset.filter(status=status)

    logs = list(queryset[:limit])

    result = []
    for log in logs:
        result.append({
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "user_username": log.user_username or (log.user.username if log.user else "Anonymous"),
            "user_email": log.user_email or (log.user.email if log.user else ""),
            "workspace_name": log.workspace_name or (log.workspace.name if log.workspace else ""),
            "workspace_id": str(log.workspace.id) if log.workspace else None,
            "interface": log.interface,
            "action_name": log.action_name,
            "status": log.status,
            "input_params": log.input_params,
            "output_summary": log.output_summary,
            "error_message": log.error_message,
            "execution_time_ms": log.execution_time_ms,
            "api_key_id": log.api_key_id
        })

    return json.dumps({
        "status": "success",
        "count": len(result),
        "logs": result
    }, indent=2)
