import logging
from celery import shared_task
from ...models import Workspace, Paper
from ...llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

@shared_task
def screen_abstract(paper_id, workspace_id):
    """
    Screens a paper abstract against workspace inclusion/exclusion criteria
    using the configured screening LLM.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        paper = Paper.objects.get(pk=paper_id)
    except (Workspace.DoesNotExist, Paper.DoesNotExist) as e:
        logger.error(f"Failed to find workspace {workspace_id} or paper {paper_id}: {str(e)}")
        return False

    provider = get_llm_provider(workspace.llm_provider)
    
    system_prompt = (
        "You are an Agentic AI Research Scanner. Screen the following abstract against the configured "
        "acceptance and rejection criteria. Return a JSON object with 'passed' (boolean) and 'reasoning' (string)."
    )
    user_prompt = (
        f"Abstract:\n{paper.abstract}\n\n"
        f"Acceptance Criteria (must satisfy to pass):\n{workspace.acceptance_criteria}\n\n"
        f"Rejection Criteria (if matched, paper is rejected):\n{workspace.rejection_criteria}"
    )

    try:
        response = provider.generate(
            prompt=user_prompt,
            system_instruction=system_prompt,
            response_schema={
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean"},
                    "reasoning": {"type": "string"}
                },
                "required": ["passed", "reasoning"]
            },
            model=workspace.screening_llm_model
        )
        
        # Simple parsing logic
        passed = response.get("passed", False) if isinstance(response, dict) else False
        reasoning = response.get("reasoning", "") if isinstance(response, dict) else str(response)

        paper.screening_status = "abstract_passed" if passed else "rejected"
        paper.screening_reasoning = reasoning
        paper.save()
        return True
    except Exception as e:
        logger.exception(f"Error screening abstract for paper {paper_id}: {str(e)}")
        return False
