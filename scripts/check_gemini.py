"""Verify a configured model server-side; never prints the API key."""
import os
from google import genai
from dotenv import load_dotenv
load_dotenv()
if not os.getenv('GEMINI_API_KEY'):raise SystemExit('GEMINI_API_KEY is not configured. No API request made.')
with genai.Client(api_key=os.environ['GEMINI_API_KEY']) as client:
    if os.getenv('GEMINI_MODEL'):
        model=client.models.get(model=os.environ['GEMINI_MODEL']);print('Available:',model.name)
    else:
        for model in client.models.list():print(model.name)
        print('Set GEMINI_MODEL to a supported model with structured JSON output.')
