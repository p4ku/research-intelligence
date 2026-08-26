"""Prompt-definition helpers shared by the two screening stages."""

from ...models import ScreeningDefinition


def get_active_screening_definition(workspace, stage):
    """Return the latest active definition for a workspace and stage, if configured."""
    return (
        ScreeningDefinition.objects.filter(workspace=workspace, stage=stage, is_active=True)
        .order_by('-version', '-created_at')
        .first()
    )


def render_user_prompt(template, **values):
    """Render the documented screening-template placeholders."""
    return template.format_map(values)
