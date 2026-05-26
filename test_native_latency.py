import asyncio
import time
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

async def test_native_audio_latency(iterations=5):
    print(f"Testing Gemini Native Audio ({MODEL}) via Live API for {iterations} iterations...")
    if not GOOGLE_API_KEY:
        print("❌ Error: GOOGLE_API_KEY not found in .env")
        return None

    client = genai.Client(api_key=GOOGLE_API_KEY)
    latencies = []
    
    # We establish the connection once (just like LiveKit does during a call)
    start_conn = time.time()
    try:
        config = {"response_modalities": ["AUDIO"]}
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            conn_time = time.time() - start_conn
            print(f"  [Info] WebSocket Connection established in {conn_time:.4f}s (This happens ONCE when the call connects)")
            
            for i in range(iterations):
                start_time = time.time()
                
                # Send text input through the realtime connection
                await session.send(input="Reply with the word 'hello'.", end_of_turn=True)
                
                # Wait for the first response chunk (TTFT - Time To First Token)
                async for response in session.receive():
                    latency = time.time() - start_time
                    
                    audio_bytes = 0
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                audio_bytes += len(part.inline_data.data)
                                
                    print(f"  [{i+1}/{iterations}] TTFT Latency: {latency:.4f}s | Received first {audio_bytes} audio bytes")
                    latencies.append(latency)
                    break # Break out of receive loop as we only want TTFT
                    
    except Exception as e:
        print(f"❌ Error connecting/sending: {e}")
        return None

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✅ Native Audio Avg TTFT: {avg:.4f}s (Min: {min(latencies):.4f}s)\n")
        return avg
    return None

if __name__ == "__main__":
    asyncio.run(test_native_audio_latency())
