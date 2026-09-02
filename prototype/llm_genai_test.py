import json
import os
from google import genai
from google.oauth2 import service_account
import dotenv

# Load environment variables from the .env file (looks recursively in parent folders)
dotenv.load_dotenv()

PROJECT_ID = "sit-disruption-t-wkzt-run-4sbq"
LOCATION = "europe-west4"      # or global

# Retrieve the service account credentials from the environment variable loaded from .env
google_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
if not google_json_str:
    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not found in environment. Make sure it is defined in .env")

# Parse the credentials JSON
info = json.loads(google_json_str)

credentials = service_account.Credentials.from_service_account_info(
    info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)

# Initialize the official google-genai client using Vertex AI
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
    credentials=credentials,
)

print("Sending request to Gemini...")
response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="What is a systematic review? Please explain it in 3–5 sentences for a graduate student."
)

print("=== Odpowiedź ===")
print(response.text)

print("\n=== Usage ===")
usage = response.usage_metadata
print(f"Prompt tokens:     {usage.prompt_token_count}")
print(f"Response tokens:   {usage.candidates_token_count}")
print(f"Total tokens:      {usage.total_token_count}")
