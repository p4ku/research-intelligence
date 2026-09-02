import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import ExtractionDefinition
from research_intelligence.services import check_workspace_access


def list_extraction_definitions_logic(user, workspace_id: str) -> str:
    """List extraction definitions configured for a workspace."""
    workspace, membership, error = check_workspace_access(user, workspace_id)
    if error:
        return error

    definitions = ExtractionDefinition.objects.filter(workspace=workspace).order_by('name', '-version')
    if not definitions.exists():
        return json.dumps({"message": f"No extraction definitions found for workspace '{workspace.name}'."}, indent=2)

    results = []
    for d in definitions:
        results.append({
            "definition_id": str(d.id),
            "name": d.name,
            "exit_metric": d.exit_metric,
            "llm_model": d.llm_model,
            "version": d.version,
            "requires_consensus": d.requires_consensus,
            "is_active": d.is_active,
            "created_at": d.created_at.isoformat(),
            "system_prompt_snippet": d.system_prompt[:120] + "..." if len(d.system_prompt) > 120 else d.system_prompt
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_extraction_definition_logic(user, definition_id: str) -> str:
    """Retrieve detailed view of an extraction definition (including prompts and response schema)."""
    try:
        d_uuid = uuid.UUID(definition_id)
    except ValueError:
        return f"Error: '{definition_id}' is not a valid UUID format."

    try:
        definition = ExtractionDefinition.objects.select_related('workspace').get(id=d_uuid)
    except ExtractionDefinition.DoesNotExist:
        from research_intelligence.models import Extraction
        if Extraction.objects.filter(id=d_uuid).exists():
            from .matrix import get_extraction_logic
            return get_extraction_logic(user, str(d_uuid))
        return f"Error: Extraction definition with ID '{definition_id}' does not exist."

    # Verify workspace access
    workspace, membership, error = check_workspace_access(user, str(definition.workspace.id))
    if error:
        return error

    details = {
        "definition_id": str(definition.id),
        "workspace_id": str(definition.workspace.id),
        "workspace_name": definition.workspace.name,
        "name": definition.name,
        "exit_metric": definition.exit_metric,
        "system_prompt": definition.system_prompt,
        "user_prompt_template": definition.user_prompt_template,
        "response_schema": definition.response_schema,
        "llm_model": definition.llm_model,
        "version": definition.version,
        "requires_consensus": definition.requires_consensus,
        "is_active": definition.is_active,
        "created_at": definition.created_at.isoformat()
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def create_extraction_definition_logic(
    user,
    workspace_id: str,
    name: str,
    system_prompt: str,
    user_prompt_template: str,
    response_schema: dict,
    exit_metric: str = None,
    exit_metric_key: str = None,
    llm_model: str = "google/gemini-3.8-flash",
    version: int = 1,
    requires_consensus: bool = False,
    is_active: bool = True
) -> str:
    """Create a new dynamic extraction definition target for a workspace."""
    workspace, membership, error = check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return error

    target_exit_metric = exit_metric or exit_metric_key

    if not isinstance(response_schema, dict):
        if isinstance(response_schema, str):
            try:
                response_schema = json.loads(response_schema)
            except Exception:
                return "Error: 'response_schema' must be a valid JSON object/dict."
        else:
            return "Error: 'response_schema' must be a JSON dictionary object."

    definition = ExtractionDefinition.objects.create(
        workspace=workspace,
        name=name,
        exit_metric=target_exit_metric,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        response_schema=response_schema,
        llm_model=llm_model,
        version=version,
        requires_consensus=requires_consensus,
        is_active=is_active
    )

    response = {
        "status": "success",
        "message": f"Extraction definition '{name}' (v{version}) created successfully.",
        "definition_id": str(definition.id),
        "workspace_id": str(workspace.id),
        "name": definition.name,
        "exit_metric": definition.exit_metric,
        "llm_model": definition.llm_model
    }
    return json.dumps(response, indent=2, cls=DjangoJSONEncoder)


def update_extraction_definition_logic(
    user,
    definition_id: str,
    name: str = None,
    exit_metric: str = None,
    exit_metric_key: str = None,
    system_prompt: str = None,
    user_prompt_template: str = None,
    response_schema: dict = None,
    llm_model: str = None,
    version: int = None,
    requires_consensus: bool = None,
    is_active: bool = None
) -> str:
    """Update an existing extraction definition."""
    try:
        d_uuid = uuid.UUID(definition_id)
    except ValueError:
        return f"Error: '{definition_id}' is not a valid UUID format."

    try:
        definition = ExtractionDefinition.objects.select_related('workspace').get(id=d_uuid)
    except ExtractionDefinition.DoesNotExist:
        return f"Error: Extraction definition with ID '{definition_id}' does not exist."

    # Verify workspace edit permissions
    workspace, membership, error = check_workspace_access(user, str(definition.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    target_exit_metric = exit_metric if exit_metric is not None else exit_metric_key

    updated_fields = []
    if name is not None:
        definition.name = name
        updated_fields.append('name')
    if target_exit_metric is not None:
        definition.exit_metric = target_exit_metric
        updated_fields.append('exit_metric')
    if system_prompt is not None:
        definition.system_prompt = system_prompt
        updated_fields.append('system_prompt')
    if user_prompt_template is not None:
        definition.user_prompt_template = user_prompt_template
        updated_fields.append('user_prompt_template')
    if response_schema is not None:
        if isinstance(response_schema, str):
            try:
                response_schema = json.loads(response_schema)
            except Exception:
                return "Error: 'response_schema' must be a valid JSON object/dict."
        definition.response_schema = response_schema
        updated_fields.append('response_schema')
    if llm_model is not None:
        definition.llm_model = llm_model
        updated_fields.append('llm_model')
    if version is not None:
        definition.version = version
        updated_fields.append('version')
    if requires_consensus is not None:
        definition.requires_consensus = requires_consensus
        updated_fields.append('requires_consensus')
    if is_active is not None:
        definition.is_active = is_active
        updated_fields.append('is_active')

    if not updated_fields:
        return json.dumps({"message": "No fields were provided to update."}, indent=2)

    definition.save(update_fields=updated_fields)

    response = {
        "status": "success",
        "message": f"Extraction definition '{definition.name}' updated successfully.",
        "definition_id": str(definition.id),
        "updated_fields": updated_fields
    }
    return json.dumps(response, indent=2, cls=DjangoJSONEncoder)


def delete_extraction_definition_logic(user, definition_id: str) -> str:
    """Delete an extraction definition from a workspace."""
    try:
        d_uuid = uuid.UUID(definition_id)
    except ValueError:
        return f"Error: '{definition_id}' is not a valid UUID format."

    try:
        definition = ExtractionDefinition.objects.select_related('workspace').get(id=d_uuid)
    except ExtractionDefinition.DoesNotExist:
        return f"Error: Extraction definition with ID '{definition_id}' does not exist."

    # Verify workspace delete permissions
    workspace, membership, error = check_workspace_access(user, str(definition.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    def_name = definition.name
    definition.delete()

    return json.dumps({
        "status": "success",
        "message": f"Extraction definition '{def_name}' (ID: {definition_id}) was successfully deleted."
    }, indent=2)
