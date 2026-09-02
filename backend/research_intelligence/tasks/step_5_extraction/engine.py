import logging
import json
import concurrent.futures
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

class EvidenceChunk(BaseModel):
    quote: str = Field(..., description="Exact quote from the text supporting the extracted value.")
    rationale: str = Field(..., description="Brief explanation of why this quote supports the value.")

class FieldExtraction(BaseModel):
    value: Any = Field(..., description="The extracted value based on the requested schema type.")
    normalized_value: Optional[str] = Field(None, description="A canonical or standardized form of the value, if applicable.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Estimated confidence score (0.0 to 1.0).")
    evidence: List[EvidenceChunk] = Field(..., description="List of evidence quotes supporting this field.")

class ExtractionResponse(BaseModel):
    fields: Dict[str, FieldExtraction] = Field(..., description="Map of extracted field names to their extraction objects.")

class ExtractionEngine:
    def __init__(self, llm_provider, max_retries: int = 3):
        self.llm_provider = llm_provider
        self.max_retries = max_retries

    def build_system_prompt(self, definition_system_prompt: str, response_schema: Dict[str, Any]) -> str:
        base_prompt = f"""{definition_system_prompt}

You must extract the information strictly following the fields requested in this schema:
{json.dumps(response_schema, indent=2)}

CRITICAL INSTRUCTIONS:
- You must return a JSON object mapping EACH requested field name to a nested object containing:
  - "value": The extracted data matching the type requested in the schema.
  - "normalized_value": A canonical string representation (optional).
  - "confidence": A float between 0.0 and 1.0 reflecting your certainty.
  - "evidence": An array of objects, each containing a "quote" (exact substring from the text) and a "rationale".
- If a field is not found in the text, you must still include the field key, but set the value to null (or empty string/list depending on the requested type), confidence to 0.0, and an empty evidence array.
"""
        return base_prompt

    def parse_and_validate(self, raw_json: str) -> Optional[ExtractionResponse]:
        try:
            # Sometimes LLMs wrap JSON in markdown block ticks
            if "```json" in raw_json:
                raw_json = raw_json.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_json:
                raw_json = raw_json.split("```")[1].split("```")[0].strip()
                
            data = json.loads(raw_json)
            # The model might return {"fields": {...}} or just the fields dictionary directly.
            if "fields" not in data:
                data = {"fields": data}
                
            return ExtractionResponse(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Validation failed: {str(e)}")
            return None

    def run_single_pass(self, text_chunk: str, system_prompt: str, user_prompt: str) -> Optional[ExtractionResponse]:
        for attempt in range(self.max_retries):
            raw_response = self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                context_data={"paper_text": text_chunk},
                temperature=0.2
            )
            
            validated = self.parse_and_validate(raw_response)
            if validated:
                return validated
                
            logger.warning(f"Single pass validation failed on attempt {attempt + 1}. Retrying...")
            
        return None

    def run_self_consistency(self, text_chunk: str, system_prompt: str, user_prompt: str, num_samples: int = 3) -> Optional[ExtractionResponse]:
        """
        Runs multiple parallel queries with high temperature, then runs a consensus resolver.
        """
        def _fetch_sample(_):
            return self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                context_data={"paper_text": text_chunk},
                temperature=0.7
            )

        worker_count = max(1, min(num_samples, 5))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            samples = list(executor.map(_fetch_sample, range(num_samples)))

        consensus_system_prompt = """You are an expert consensus resolver.
You are given 3 independent extraction attempts from the same source document.
Your task is to analyze these samples, resolve any contradictions, select the most accurate and supported values, and produce a final, definitive JSON extraction object.
Ensure your final response strictly adheres to the requested JSON structure."""

        consensus_user_prompt = "Here are the samples:\n\n"
        for i, sample in enumerate(samples):
            consensus_user_prompt += f"--- Sample {i+1} ---\n{sample}\n\n"

        for attempt in range(self.max_retries):
            raw_consensus = self.llm_provider.generate(
                prompt=consensus_user_prompt,
                system_prompt=consensus_system_prompt,
                temperature=0.0
            )
            
            validated = self.parse_and_validate(raw_consensus)
            if validated:
                return validated
                
            logger.warning(f"Consensus validation failed on attempt {attempt + 1}. Retrying...")
            
        return None

    def execute(self, paper_text: str, definition_system_prompt: str, user_prompt: str, response_schema: Dict[str, Any], requires_consensus: bool) -> tuple[Optional[ExtractionResponse], str]:
        system_prompt = self.build_system_prompt(definition_system_prompt, response_schema)
        
        if requires_consensus:
            logger.info("Running self-consistency consensus extraction (3 samples)...")
            result = self.run_self_consistency(paper_text, system_prompt, user_prompt)
            method = "self_consistency"
        else:
            logger.info("Running single-pass extraction...")
            result = self.run_single_pass(paper_text, system_prompt, user_prompt)
            method = "single_pass"
            
        return result, method
