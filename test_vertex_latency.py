import asyncio
import time
import os
from google import genai
from google.genai import types

# Configure Google Cloud Credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/devbhangale/Developer/git-docify/opensourcenav/backend/gcp.json"

PROJECT = "easy-git"
LOCATION = "asia-south1"
MODEL = "gemini-2.5-flash"

async def test_vertex_audio_latency(iterations=3):
    print(f"Testing Vertex AI ({MODEL}) standard text in {LOCATION} for {iterations} iterations...")
    
    client = genai.Client(
        vertexai=True,
        project=PROJECT,
        location=LOCATION
    )
    
    latencies = []
    
    try:
        for i in range(iterations):
            start_time = time.time()
            
            response = client.models.generate_content(
                model=MODEL,
                contents="Reply with the word 'hello'.",
            )
            
            latency = time.time() - start_time
            print(f"  [{i+1}/{iterations}] Latency: {latency:.4f}s | Response: '{response.text.strip()}'")
            latencies.append(latency)
                    
    except Exception as e:
        print(f"❌ Error connecting/sending: {e}")
        return None

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✅ Vertex AI ({LOCATION}) Avg TTFT: {avg:.4f}s (Min: {min(latencies):.4f}s)\n")
        return avg
    return None

if __name__ == "__main__":
    asyncio.run(test_vertex_audio_latency())
