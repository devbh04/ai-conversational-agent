import asyncio
from livekit.plugins.google.realtime.realtime_api import RealtimeModel

async def main():
    model = RealtimeModel(
        model="gemini-live-2.5-flash-native-audio",
        vertexai=True,
        api_key="TEST_API_KEY",
        project="test-project",
        location="us-central1"
    )
    print("Model initialized:", model._client.api_client.vertexai)
    
asyncio.run(main())
