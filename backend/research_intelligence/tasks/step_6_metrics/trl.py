import logging
import time
from celery import shared_task
from django.core.files.storage import default_storage
from ...models import Paper, PaperMetric
from ...llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

TRL_SYSTEM_PROMPT = """Technology Readiness Level (TRL) is a scale used to estimate the maturity of a technology and its readiness for deployment.
Originally developed by NASA, it is now widely used in R&D projects, tech startups, EU grants (e.g., Horizon Europe), industry, defense, and deep tech.

The scale consists of 9 levels:
TRL 1: Basic principles observed and reported
TRL 2: Technology concept and/or application formulated
TRL 3: Analytical and experimental critical function and/or characteristic proof of concept
TRL 4: Technology validated in lab
TRL 5: Technology validated in relevant environment
TRL 6: Technology demonstrated in relevant environment
TRL 7: System prototype demonstration in operational environment
TRL 8: System complete and qualified
TRL 9: Actual system proven in operational environment

Simplification:
TRL 1–3 → Research and ideation
TRL 4–6 → Prototyping and testing
TRL 7–9 → Ready product / deployment

You are an expert in technology evaluation and innovation. Your task is to assess the current TRL based on the provided text from a research publication. Justify your assessment."""

@shared_task
def assess_technology_readiness(paper_id, pipeline_run_id=None):
    """
    Evaluates the Technology Readiness Level (TRL) of a given paper.
    Updates or creates a PaperMetric record with the TRL score and reasoning per pipeline_run.
    """
    try:
        from ...models import PipelineRun
        paper = Paper.objects.select_related('workspace', 'pipeline_run').get(pk=paper_id)
        workspace = paper.workspace
        pipeline_run = None
        if pipeline_run_id:
            pipeline_run = PipelineRun.objects.filter(pk=pipeline_run_id).first()
        if not pipeline_run:
            pipeline_run = paper.pipeline_run
    except Paper.DoesNotExist:
        logger.error(f"Paper {paper_id} does not exist.")
        return False

    logger.info(f"Starting TRL assessment for Paper {paper_id}")

    # Retrieve document text (from OCR or fallback to abstract)
    if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
        with default_storage.open(paper.converted_md_path, 'rb') as f:
            raw_content = f.read()
        paper_text = raw_content.decode("utf-8") if isinstance(raw_content, bytes) else str(raw_content)
    else:
        paper_text = paper.abstract

    provider = get_llm_provider(workspace.llm_provider)

    # Use JSON Schema to ensure a clean 1-9 int and reasoning string
    response_schema = {
        "type": "object",
        "properties": {
            "trl_score": {
                "type": "integer",
                "description": "An integer from 1 to 9 representing the Technology Readiness Level."
            },
            "trl_reasoning": {
                "type": "string",
                "description": "Short justification explaining why this specific TRL was assigned."
            },
            "trl_evidence": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of exact quotes from the text that serve as evidence for this TRL."
            }
        },
        "required": ["trl_score", "trl_reasoning", "trl_evidence"]
    }

    user_prompt = f"Analyze the following text from a scientific publication and assess its Technology Readiness Level.\n\nPublication text:\n{paper_text}"

    try:
        response = provider.generate(
            prompt=user_prompt,
            system_instruction=TRL_SYSTEM_PROMPT,
            response_schema=response_schema,
            temperature=0.1  # Low temp for deterministic analytical assessment
        )

        trl_score = response.get("trl_score")
        trl_reasoning = response.get("trl_reasoning")
        trl_evidence = response.get("trl_evidence", [])

        if trl_score is not None:
            trl_data = {
                "trl_score": trl_score,
                "trl_reasoning": trl_reasoning,
                "trl_evidence": trl_evidence
            }
            # Update or create the paper metric per pipeline run
            metric, created = PaperMetric.objects.get_or_create(
                paper=paper,
                pipeline_run=pipeline_run,
                workspace=workspace,
                defaults={
                    "metrics_data": trl_data
                }
            )
            
            if not created:
                metric.metrics_data.update(trl_data)
                metric.save(update_fields=['metrics_data'])

            logger.info(f"Successfully assessed TRL {trl_score} for Paper {paper_id}")
            return True
        else:
            logger.error(f"LLM failed to return a valid TRL score for Paper {paper_id}")
            return False

    except Exception as e:
        logger.exception(f"Error during TRL assessment for paper {paper_id}: {str(e)}")
        return False
