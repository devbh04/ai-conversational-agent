import time
import os
import requests
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env")

# Configuration
HF_URL = "https://devbh04-voice-agent.hf.space/health" 
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

def test_hf_latency(iterations=3):
    print(f"Testing HF Spaces latency ({HF_URL}) for {iterations} iterations...")
    latencies = []
    for i in range(iterations):
        start_time = time.time()
        try:
            response = requests.get(HF_URL, timeout=10)
            latency = time.time() - start_time
            print(f"  [{i+1}/{iterations}] Status {response.status_code} | Latency: {latency:.4f}s")
            latencies.append(latency)
        except Exception as e:
            print(f"  [{i+1}/{iterations}] Error: {e}")
    
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✅ HF Spaces Avg Latency: {avg:.4f}s (Min: {min(latencies):.4f}s)\n")
        return avg
    return None

def test_gemini_latency(iterations=3):
    print(f"Testing Gemini API latency ({MODEL}) for {iterations} iterations...")
    if not GOOGLE_API_KEY:
        print("❌ Error: GOOGLE_API_KEY not found in .env")
        return None
        
    client = genai.Client(api_key=GOOGLE_API_KEY)
    latencies = []
    for i in range(iterations):
        start_time = time.time()
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents="Say 'hello' in one word.",
            )
            latency = time.time() - start_time
            print(f"  [{i+1}/{iterations}] Response: '{response.text.strip()}' | Latency: {latency:.4f}s")
            latencies.append(latency)
        except Exception as e:
            print(f"  [{i+1}/{iterations}] Error: {e}")

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✅ Gemini Avg Latency: {avg:.4f}s (Min: {min(latencies):.4f}s)\n")
        return avg
    return None

if __name__ == "__main__":
    print("=== Latency Test ===")
    hf_latency = test_hf_latency(iterations=3)
    gemini_latency = test_gemini_latency(iterations=3)
    
    if hf_latency and gemini_latency:
        print(f"=== Final Average Results ===")
        print(f"HF Spaces Avg: {hf_latency:.4f}s")
        print(f"Gemini Avg:    {gemini_latency:.4f}s")
        print(f"Combined Avg:  {(hf_latency + gemini_latency):.4f}s")
