import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import PromptTemplate
from .workspaces import _check_workspace_access


def list_prompt_templates_logic(user, workspace_id: str, step_name: str = None) -> str:
    """List prompt templates configured for a workspace, optionally filtered by step_name."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
    if error:
        return error

    query = PromptTemplate.objects.filter(workspace=workspace)
    if step_name:
        query = query.filter(step_name=step_name)

    templates = query.order_by('step_name', '-version')
    if not templates.exists():
        filter_msg = f" for step '{step_name}'" if step_name else ""
        return json.dumps({"message": f"No prompt templates found for workspace '{workspace.name}'{filter_msg}."}, indent=2)

    results = []
    for t in templates:
        results.append({
            "template_id": str(t.id),
            "step_name": t.step_name,
            "version": t.version,
            "is_active": t.is_active,
            "updated_at": t.updated_at.isoformat(),
            "prompt_snippet": t.prompt_text[:120] + "..." if len(t.prompt_text) > 120 else t.prompt_text
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_prompt_template_logic(
    user,
    template_id: str = None,
    workspace_id: str = None,
    step_name: str = None,
    version: int = None
) -> str:
    """Retrieve detailed view of a prompt template (including full prompt_text and metadata)."""
    if template_id:
        try:
            t_uuid = uuid.UUID(template_id)
        except ValueError:
            return f"Error: '{template_id}' is not a valid UUID format."

        try:
            template = PromptTemplate.objects.select_related('workspace').get(id=t_uuid)
        except PromptTemplate.DoesNotExist:
            return f"Error: Prompt template with ID '{template_id}' does not exist."
    elif workspace_id and step_name:
        workspace, membership, error = _check_workspace_access(user, workspace_id)
        if error:
            return error

        query = PromptTemplate.objects.filter(workspace=workspace, step_name=step_name)
        if version is not None:
            query = query.filter(version=version)
        else:
            query = query.order_by('-version')

        template = query.first()
        if not template:
            return f"Error: Prompt template for step '{step_name}' not found in workspace '{workspace.name}'."
    else:
        return "Error: Must provide either template_id or both workspace_id and step_name."

    # Verify workspace access
    workspace, membership, error = _check_workspace_access(user, str(template.workspace.id))
    if error:
        return error

    details = {
        "template_id": str(template.id),
        "workspace_id": str(template.workspace.id),
        "workspace_name": template.workspace.name,
        "step_name": template.step_name,
        "version": template.version,
        "is_active": template.is_active,
        "updated_at": template.updated_at.isoformat(),
        "prompt_text": template.prompt_text
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def create_prompt_template_logic(
    user,
    workspace_id: str,
    step_name: str,
    prompt_text: str,
    version: int = 1,
    is_active: bool = True
) -> str:
    """Create a new prompt template override for a workflow step in a workspace."""
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return error

    if not step_name or not step_name.strip():
        return "Error: step_name is required (e.g. 'scraper_query', 'abstract_screening', 'parameter_extraction')."

    if not prompt_text or not prompt_text.strip():
        return "Error: prompt_text is required and cannot be blank."

    # Check for existing version conflict
    existing = PromptTemplate.objects.filter(workspace=workspace, step_name=step_name.strip(), version=version).first()
    if existing:
        return (
            f"Error: Prompt template for step '{step_name}' with version {version} already exists. "
            f"Please update existing template '{existing.id}' or specify a new version number."
        )

    try:
        template = PromptTemplate.objects.create(
            workspace=workspace,
            step_name=step_name.strip(),
            prompt_text=prompt_text.strip(),
            version=version,
            is_active=is_active
        )
        return json.dumps({
            "success": True,
            "message": f"Successfully created prompt template for step '{template.step_name}' (v{template.version}) in workspace '{workspace.name}'.",
            "template_id": str(template.id),
            "step_name": template.step_name,
            "version": template.version,
            "is_active": template.is_active
        }, indent=2)
    except Exception as e:
        return f"Error creating prompt template: {e}"


def update_prompt_template_logic(
    user,
    template_id: str,
    prompt_text: str = None,
    version: int = None,
    is_active: bool = None
) -> str:
    """Update an existing prompt template (prompt_text, version, or active status)."""
    try:
        t_uuid = uuid.UUID(template_id)
    except ValueError:
        return f"Error: '{template_id}' is not a valid UUID format."

    try:
        template = PromptTemplate.objects.select_related('workspace').get(id=t_uuid)
    except PromptTemplate.DoesNotExist:
        return f"Error: Prompt template with ID '{template_id}' does not exist."

    workspace, membership, error = _check_workspace_access(user, str(template.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    if prompt_text is not None:
        if not prompt_text.strip():
            return "Error: prompt_text cannot be blank."
        template.prompt_text = prompt_text.strip()

    if version is not None:
        template.version = version

    if is_active is not None:
        template.is_active = is_active

    template.save()

    return json.dumps({
        "success": True,
        "message": f"Prompt template for step '{template.step_name}' (v{template.version}) successfully updated.",
        "template_id": str(template.id),
        "step_name": template.step_name,
        "version": template.version,
        "is_active": template.is_active
    }, indent=2)


def delete_prompt_template_logic(user, template_id: str) -> str:
    """Delete a prompt template definition."""
    try:
        t_uuid = uuid.UUID(template_id)
    except ValueError:
        return f"Error: '{template_id}' is not a valid UUID format."

    try:
        template = PromptTemplate.objects.select_related('workspace').get(id=t_uuid)
    except PromptTemplate.DoesNotExist:
        return f"Error: Prompt template with ID '{template_id}' does not exist."

    workspace, membership, error = _check_workspace_access(user, str(template.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    step_name = template.step_name
    version = template.version
    template.delete()

    return json.dumps({
        "success": True,
        "message": f"Successfully deleted prompt template for step '{step_name}' (v{version})."
    }, indent=2)
