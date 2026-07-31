import os
import json
from pathlib import Path

from google import genai
from google.genai import types
from google.oauth2 import service_account
import dotenv

# Load environment variables (looks recursively in parent folders)
dotenv.load_dotenv()

PROJECT_ID = "sit-disruption-t-wkzt-run-4sbq"
LOCATION = "eu"  # or "global"
MODEL = "gemini-3.6-flash"

# Resolve paths dynamically relative to script location so it runs from anywhere
SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR / "paper.pdf"
OUT_MD = SCRIPT_DIR / "paper.md"

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
CREDS_FILE = "piotr_personal-credentials.json"

PROMPT = """
Convert the attached PDF into clean Markdown.

Requirements:
- preserve headings
- preserve lists
- preserve tables as Markdown tables when possible
- preserve equations in LaTeX when present
- preserve code blocks
- do not summarize
- output only Markdown, with no code fences or extra commentary
"""

# Authenticate: Try local JSON credentials file first (either in current dir or script dir),
# fallback to GOOGLE_SERVICE_ACCOUNT_JSON from environment/.env.
creds = None
possible_creds_paths = [
    Path(CREDS_FILE),
    SCRIPT_DIR / CREDS_FILE,
    SCRIPT_DIR.parent / CREDS_FILE,
]

for p in possible_creds_paths:
    if p.exists():
        creds = service_account.Credentials.from_service_account_file(
            str(p),
            scopes=SCOPES,
        )
        break

if not creds:
    google_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if google_json_str:
        info = json.loads(google_json_str)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=SCOPES,
        )
    else:
        raise FileNotFoundError(
            f"Could not find service account credentials. Placed '{CREDS_FILE}' in one of {possible_creds_paths} "
            "or set GOOGLE_SERVICE_ACCOUNT_JSON in your environment/.env file."
        )

# Initialize the official google-genai client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
    credentials=creds,
)

if not PDF_PATH.exists():
    # Try current directory fallback
    if Path("paper.pdf").exists():
        PDF_PATH = Path("paper.pdf")
        OUT_MD = Path("paper.md")
    else:
        raise FileNotFoundError(f"PDF file not found at {PDF_PATH}")

pdf_bytes = PDF_PATH.read_bytes()
pdf_part = types.Part.from_bytes(
    data=pdf_bytes,
    mime_type="application/pdf",
)

# Optional: count tokens before generation
token_info = client.models.count_tokens(
    model=MODEL,
    contents=[pdf_part, PROMPT],
)
print("Estimated input tokens:", token_info.total_tokens)

print(f"Generating markdown from {PDF_PATH} using {MODEL} (streaming)...")
response = client.models.generate_content_stream(
    model=MODEL,
    contents=[pdf_part, PROMPT],
    config=types.GenerateContentConfig(
        temperature=0,
        # max_output_tokens=8192,
    ),
)

usage = None
try:
    with OUT_MD.open("w", encoding="utf-8") as f:
        for chunk in response:
            text = chunk.text
            if text:
                f.write(text)
                f.flush()
            if chunk.usage_metadata and chunk.usage_metadata.total_token_count is not None:
                usage = chunk.usage_metadata
except Exception as e:
    print(f"\nWarning: Streaming was interrupted by an exception: {e}")
    print("Saving the markdown generated so far and exiting gracefully.")

print(f"Saved Markdown to: {OUT_MD}")

if usage:
    print("\nToken usage")
    print("-" * 40)
    print(f"Prompt     : {usage.prompt_token_count}")
    print(f"Completion : {usage.candidates_token_count}")
    print(f"Total      : {usage.total_token_count}")
else:
    print("\nNo token usage metadata returned in response chunks.")
