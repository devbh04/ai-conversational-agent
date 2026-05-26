import os
from google import genai

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/devbhangale/Developer/git-docify/opensourcenav/backend/gcp.json"

PROJECT = "easy-git"
REGIONS = [
    "us-central1", "us-east1", "us-east4", "us-west1",
    "europe-west4", "europe-west1", "europe-west3", "europe-west2",
    "asia-south1", "asia-southeast1", "asia-northeast1",
    "me-central1", "me-central2"
]

def list_vertex_models():
    found_regions = {}
    
    for location in REGIONS:
        print(f"Checking {location}...", end=" ")
        try:
            client = genai.Client(vertexai=True, project=PROJECT, location=location)
            models = client.models.list()
            
            audio_capable = []
            for m in models:
                name = getattr(m, 'name', str(m))
                if "audio" in name.lower() or "live" in name.lower() or "3.1" in name.lower():
                    audio_capable.append(name.split('/')[-1])
                    
            if audio_capable:
                print(f"✅ Found {len(audio_capable)} models")
                found_regions[location] = sorted(list(set(audio_capable)))
            else:
                print("❌ No models found")
                
        except Exception as e:
            print(f"❌ Error/Unavailable ({e})")

    print("\n\n=== SUMMARY OF REGIONS WITH NATIVE AUDIO/LIVE MODELS ===")
    for region, models in found_regions.items():
        print(f"\n📍 {region}:")
        for m in models:
            print(f"   - {m}")

if __name__ == "__main__":
    list_vertex_models()
