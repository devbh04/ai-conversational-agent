import asyncio
import time
import os
from google import genai

# Configure Google Cloud Credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/devbhangale/Developer/git-docify/opensourcenav/backend/gcp.json"

PROJECT = "easy-git"
MODEL = "gemini-live-2.5-flash-native-audio"

REGIONS = [
    "us-central1",
    "us-east1",
    "us-east4",
    "us-west1",
    "europe-west1",
    "europe-west4"
]

ITERATIONS = 5

async def test_region(region):
    print(f"\n==============================================")
    print(f"Testing {region}...")
    
    client = genai.Client(vertexai=True, project=PROJECT, location=region)
    latencies = []
    
    try:
        config = {"response_modalities": ["AUDIO"]}
        start_conn = time.time()
        
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            conn_time = time.time() - start_conn
            print(f"  [Info] Connection established in {conn_time:.4f}s")
            
            for i in range(ITERATIONS):
                start_time = time.time()
                await session.send(input=f"Reply with a short word number {i}.", end_of_turn=True)
                
                async for response in session.receive():
                    latency = time.time() - start_time
                    latencies.append(latency)
                    print(f"  [{i+1}/{ITERATIONS}] TTFT: {latency:.4f}s")
                    break # Break to move to next iteration
                
                # Small sleep to let server catch up before next turn
                await asyncio.sleep(0.5)
                
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None
        
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✅ {region} Avg TTFT: {avg:.4f}s (Min: {min(latencies):.4f}s)")
        return avg
    return None

async def main():
    results = {}
    for r in REGIONS:
        avg = await test_region(r)
        if avg is not None:
            results[r] = avg
            
    if results:
        print("\n\n=== LATENCY LEADERBOARD ===")
        # Sort by lowest average latency
        sorted_results = sorted(results.items(), key=lambda x: x[1])
        for i, (region, avg) in enumerate(sorted_results):
            print(f"{i+1}. {region}: {avg:.4f}s avg TTFT")

if __name__ == "__main__":
    asyncio.run(main())
