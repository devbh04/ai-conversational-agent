import os
from google import genai
import asyncio

async def test():
    try:
        client = genai.Client(vertexai=True, project="test", location="us-central1", api_key="TEST")
        print("Success initialization")
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
