import logging
import time
from celery import shared_task, group
from django.utils import timezone
from django.core.files.storage import default_storage
from ...models import Workspace, Paper, Extraction, ExtractionDefinition, AuditTrail
from ...llm_providers import get_llm_provider
from .engine import ExtractionEngine

logger = logging.getLogger(__name__)

@shared_task
def run_extraction_for_definition(paper_id, definition_id):
    """
    Idempotent worker task that runs the advanced ExtractionEngine for a single definition.
    Supports retries, self-consistency loops, and provenance evidence tracking.
    """
    start_time = time.time()
    
    try:
        paper = Paper.objects.get(pk=paper_id)
        definition = ExtractionDefinition.objects.get(pk=definition_id)
        workspace = paper.workspace
    except (Paper.DoesNotExist, ExtractionDefinition.DoesNotExist) as e:
        logger.error(f"Missing entities: {str(e)}")
        return False

    # 1. Idempotency Check (prevent duplicates if version hasn't changed)
    existing_extraction = Extraction.objects.filter(
        paper=paper,
        extraction_definition=definition,
        version_info__version=definition.version
    ).first()
    
    if existing_extraction:
        logger.info(f"Extraction already exists for Paper {paper_id} and Definition {definition_id} (v{definition.version}). Skipping.")
        return True

    logger.info(f"Starting extraction for Paper {paper_id} using Definition {definition.name}")

    # 2. Retrieve layout markdown text
    if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
        with default_storage.open(paper.converted_md_path, 'rb') as f:
            raw_content = f.read()
        paper_text = raw_content.decode("utf-8") if isinstance(raw_content, bytes) else str(raw_content)
    else:
        paper_text = paper.abstract  # Fallback to abstract if OCR isn't completed

    # 3. Instantiate LLM Provider and Advanced Engine
    llm_provider = get_llm_provider(workspace.llm_provider)
    engine = ExtractionEngine(llm_provider=llm_provider, max_retries=3)

    user_prompt = definition.user_prompt_template.format(paper_text=paper_text)

    # 4. Execute Advanced Extraction
    extraction_response, method = engine.execute(
        paper_text=paper_text,
        definition_system_prompt=definition.system_prompt,
        user_prompt=user_prompt,
        response_schema=definition.response_schema,
        requires_consensus=definition.requires_consensus
    )

    if not extraction_response:
        logger.error(f"Engine completely failed to extract valid data for Paper {paper_id} and Definition {definition.name}")
        return False

    fields_dict = extraction_response.model_dump()["fields"]
    
    # 5. Compute global confidence and validation status
    confidences = [f.get("confidence", 0.0) for f in fields_dict.values()]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    review_required = False
    validation_status = "pass"
    
    if avg_confidence < 0.65:
        review_required = True
        validation_status = "warn"
        
    for field_data in fields_dict.values():
        if not field_data.get("evidence"):
            validation_status = "warn"
            review_required = True

    # 6. Store Extraction Result
    version_info = {
        "version": definition.version,
        "llm_model": definition.llm_model,
        "provider": workspace.llm_provider
    }

    Extraction.objects.create(
        workspace=workspace,
        paper=paper,
        extraction_definition=definition,
        category=definition.name,
        fields_data=fields_dict,
        version_info=version_info,
        validation_status=validation_status,
        review_required=review_required,
        confidence_score=avg_confidence,
        confidence_method=method
    )

    logger.info(f"Successfully extracted {definition.name} for Paper {paper_id} in {time.time() - start_time:.2f}s")
    return True


@shared_task
def extract_custom_variables(paper_id, workspace_id):
    """
    Orchestrator task that triggers parallel advanced extractions via Celery group.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist as e:
        logger.error(f"Failed to find workspace {workspace_id}: {str(e)}")
        return False

    active_definitions = workspace.extraction_definitions.filter(is_active=True)
    if not active_definitions.exists():
        logger.warning(f"No active extraction definitions found for workspace {workspace_id}")
        return True

    # Build a Celery group of parallel independent tasks
    task_signatures = [
        run_extraction_for_definition.s(paper_id, d.id) 
        for d in active_definitions
    ]
    
    extraction_group = group(task_signatures)
    extraction_group.apply_async()
    
    logger.info(f"Dispatched {len(task_signatures)} extraction tasks for Paper {paper_id}")
    return True
