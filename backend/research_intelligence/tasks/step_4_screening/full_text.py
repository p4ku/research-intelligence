import logging
from celery import shared_task
from ...models import Workspace, Paper
from ...llm_providers import get_llm_provider
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

@shared_task
def screen_full_text(paper_id, workspace_id):
    """
    Screens full paper text against workspace inclusion/exclusion criteria
    using the configured screening LLM.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        paper = Paper.objects.get(pk=paper_id)
    except (Workspace.DoesNotExist, Paper.DoesNotExist) as e:
        logger.error(f"Failed to find workspace {workspace_id} or paper {paper_id}: {str(e)}")
        return False

    provider = get_llm_provider(workspace.llm_provider)

    try:
        if paper.converted_md_path:
            with default_storage.open(paper.converted_md_path, 'rb') as f:
                raw_content = f.read()
            paper_text = raw_content.decode("utf-8") if isinstance(raw_content, bytes) else str(raw_content)
        else:
            paper_text = paper.abstract

        system_prompt = (
            "You are an Agentic AI Research Scanner. Screen the following full text of the paper against the configured "
            "acceptance and rejection criteria. Return a JSON object with 'passed' (boolean) and 'reasoning' (string)."
        )
        user_prompt = (
            f"Full Text:\n{paper_text[:20000]}\n\n"  # Truncate content to fit window context safely
            f"Acceptance Criteria (must satisfy to pass):\n{workspace.acceptance_criteria}\n\n"
            f"Rejection Criteria (if matched, paper is rejected):\n{workspace.rejection_criteria}"
        )

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

        paper.screening_status = "full_text_passed" if passed else "rejected"
        paper.screening_reasoning = reasoning
        paper.save()
        return True
    except Exception as e:
        logger.exception(f"Error screening full text for paper {paper_id}: {str(e)}")
        return False
