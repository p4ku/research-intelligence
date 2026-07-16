import os
import json
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
import dotenv

# Load environment variables (looks recursively in parent folders)
dotenv.load_dotenv()

PROJECT_ID = "sit-disruption-t-wkzt-run-4sbq"
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

# Initialize AuthorizedSession for REST API call
session = AuthorizedSession(creds)

# Use us-central1 as the gateway endpoint to query the list of available locations
url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations"

print(f"Retrieving available Vertex AI locations for Project: {PROJECT_ID}...")

try:
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        locations = data.get("locations", [])
        
        # Extract and sort location IDs
        location_ids = sorted([loc.get("locationId") for loc in locations if loc.get("locationId")])
        
        print("\nAvailable Vertex AI Locations/Regions:")
        print("-" * 50)
        print(f"{'#':<4} | {'Location / Region ID':<40}")
        print("-" * 50)
        
        for idx, loc_id in enumerate(location_ids, 1):
            print(f"{idx:<4} | {loc_id:<40}")
            
        print("-" * 50)
        print(f"Total locations found: {len(location_ids)}\n")
        
    else:
        print(f"Failed to retrieve locations. API returned status: {response.status_code}")
        print("Response details:")
        print(response.text)
        
except Exception as e:
    print(f"Error querying locations API: {e}")
