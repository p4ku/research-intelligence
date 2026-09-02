import json
import os
from pathlib import Path

from google import genai
from google.genai import types
from google.oauth2 import service_account
import dotenv

# Load environment variables from .env file
dotenv.load_dotenv()

PROJECT_ID = "sit-disruption-t-wkzt-run-4sbq"
LOCATION = "eu"   # regional endpoint for Vertex AI multimodal inputs
MODEL = "gemini-3.8-flash"
PDF_PATH = Path(__file__).resolve().parent / "paper.pdf"

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

PROMPT = """
You are helping with a systematic review.

Read the paper and estimate the Technology Readiness Level (TRL)
of the core technology advanced by the paper, on the nine-level EU scale.

Return ONLY valid JSON with exactly this schema:
{
  "trl": 1-9,
  "confidence": "low|medium|high",
  "evidence": "short supporting quote or paraphrase from the paper",
  "reasoning": "brief explanation"
}

If the TRL is not explicit, infer the most likely TRL and say so in reasoning.
Keep evidence short.
"""

schema = {
    "type": "object",
    "properties": {
        "trl": {"type": "integer", "minimum": 1, "maximum": 9},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "evidence": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["trl", "confidence", "evidence", "reasoning"],
    "propertyOrdering": ["trl", "confidence", "evidence", "reasoning"],
}

# Resolve the service account credentials from environment variables
google_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
if not google_json_str:
    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not found in environment. Make sure it is defined in .env")

info = json.loads(google_json_str)

creds = service_account.Credentials.from_service_account_info(
    info,
    scopes=SCOPES,
)

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
    credentials=creds,
)

if not PDF_PATH.exists():
    raise FileNotFoundError(
        f"PDF file not found at '{PDF_PATH}'. Please put a PDF document named 'paper.pdf' in the same directory "
        "as this script to run it."
    )

with PDF_PATH.open("rb") as f:
    pdf_bytes = f.read()

pdf_part = types.Part.from_bytes(
    data=pdf_bytes,
    mime_type="application/pdf",
)

print(f"Sending multimodal request to Gemini ({MODEL}) with file {PDF_PATH}...")
response = client.models.generate_content(
    model=MODEL,
    contents=[pdf_part, PROMPT],
    config=types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=256,
        response_mime_type="application/json",
        response_json_schema=schema,
    ),
)

result = response.parsed
if result is None:
    result = json.loads(response.text)

print("=" * 80)
print("TRL ASSESSMENT")
print("=" * 80)
print(f"TRL        : {result['trl']}")
print(f"Confidence : {result['confidence']}")

print("\nEvidence")
print("-" * 80)
print(result["evidence"])

print("\nReasoning")
print("-" * 80)
print(result["reasoning"])

print("\nToken usage")
print("-" * 80)
usage = response.usage_metadata
print(f"Prompt     : {usage.prompt_token_count}")
print(f"Completion : {usage.candidates_token_count}")
print(f"Total      : {usage.total_token_count}")
