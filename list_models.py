import os
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()
api_key = os.environ.get('GOOGLE_API_KEY')
if not api_key:
    print("GOOGLE_API_KEY not found in .env")
    exit(1)

client = genai.Client(api_key=api_key)

print("Fetching Gemini 2.5 models allowed with your key...")
try:
    for m in client.models.list():
        if "2.5" in m.name and "flash" in m.name:
            methods = getattr(m, 'supported_generation_methods', [])
            print(f"Model: {m.name}")
            print(f"  Supported methods: {methods}")
except Exception as e:
    print(f"Error: {e}")
