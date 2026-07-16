import sys
import os
import json
from pathlib import Path

from google import genai
from google.oauth2 import service_account
import dotenv

# Load environment variables (looks recursively in parent folders)
dotenv.load_dotenv()

PROJECT_ID = "sit-disruption-t-wkzt-run-4sbq"
LOCATION = sys.argv[1] if len(sys.argv) > 1 else "eu"

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
CREDS_FILE = "piotr_personal-credentials.json"

SCRIPT_DIR = Path(__file__).resolve().parent

# Authenticate: Try local JSON credentials file first,
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

print(f"Retrieving models from Vertex AI (Project: {PROJECT_ID}, Location: {LOCATION})...")

try:
    models = client.models.list()
    
    print("\nAvailable Models:")
    print("-" * 80)
    print(f"{'Model Name':<50} | {'Version':<10}")
    print("-" * 80)
    
    count = 0
    for model in models:
        name = model.name or "N/A"
        version = model.version or "N/A"
        print(f"{name:<50} | {version:<10}")
        count += 1
        
    print("-" * 80)
    print(f"Total models found: {count}\n")
    
except Exception as e:
    print(f"Error listing models: {e}")
