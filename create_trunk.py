import asyncio
import os
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env")

async def main():
    lkapi = api.LiveKitAPI()
    try:
        sip = lkapi.sip
        
        address = os.getenv("VOBIZ_SIP_DOMAIN")
        username = os.getenv("VOBIZ_USERNAME")
        password = os.getenv("VOBIZ_PASSWORD")
        number = os.getenv("VOBIZ_OUTBOUND_NUMBER")
        
        if not all([address, username, password, number]):
            print("Missing VoBiz credentials in .env")
            return
            
        print(f"Creating SIP Trunk for: {address}")
        
        # Create trunk info
        trunk_info = api.SIPOutboundTrunkInfo(
            name="VoBiz Outbound Trunk",
            address=address,
            numbers=[number],
            auth_username=username,
            auth_password=password,
        )
        
        # Create trunk
        trunk = await sip.create_sip_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(
                trunk=trunk_info
            )
        )
        
        print("\n✅ Successfully created outbound SIP trunk!")
        print(f"Your NEW Trunk ID is: {trunk.sip_trunk_id}")
        print("Please replace the SIP_TRUNK_ID in your .env file with this ID.")
        
    except Exception as e:
        print(f"Error creating trunk: {e}")
    finally:
        await lkapi.aclose()

if __name__ == "__main__":
    asyncio.run(main())
