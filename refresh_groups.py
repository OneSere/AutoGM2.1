#!/usr/bin/env python3
"""
Helper script to manually refresh groups list in Firebase
Run this to update the groups list if you add/remove groups
"""

import asyncio
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
import pyrebase

# Firebase Config (same as main.py)
firebase_config = {
    "apiKey": "AIzaSyDV7ASwCt5zeeJyTGSOslcx-yj-oDU2JbY",
    "authDomain": "autogm-b2a47.firebaseapp.com",
    "databaseURL": "https://autogm-b2a47-default-rtdb.firebaseio.com",
    "projectId": "autogm-b2a47",
    "storageBucket": "autogm-b2a47.appspot.com",
    "messagingSenderId": "469637394660",
    "appId": "1:469637394660:web:b1b0e5ba394677cf9c7cf1"
}
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

API_ID = 25843334
API_HASH = "e752bb9ebc151b7e36741d7ead8e4fd0"
PHONE = "+919351044618"

async def refresh_groups():
    """Refresh groups list in Firebase"""
    print("🔐 Logging into Telegram...")
    
    # Try to load existing session
    session_str = db.child("session").get().val()
    if session_str:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                print("✅ Auto-login successful!")
            else:
                print("❌ Session expired, need fresh login")
                await client.disconnect()
                return
        except Exception as e:
            print(f"❌ Session login failed: {e}")
            await client.disconnect()
            return
    else:
        print("❌ No session found, need fresh login")
        return
    
    print("📋 Fetching groups from Telegram...")
    groups_data = []
    group_number = 1
    
    try:
        async for dialog in client.iter_dialogs():
            # Only include groups and channels, never personal users
            if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                group_info = {
                    "number": group_number,
                    "id": dialog.id,
                    "title": dialog.title,
                    "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                    "type": "group" if dialog.is_group else "channel",
                    "participants_count": getattr(dialog.entity, 'participants_count', 0)
                }
                groups_data.append(group_info)
                print(f"✅ Found group {group_number}: {dialog.title} (ID: {dialog.id})")
                group_number += 1
        
        if groups_data:
            # Create the groups list in Firebase
            groups_dict = {}
            for group in groups_data:
                groups_dict[str(group["number"])] = f"{group['number']}. {group['title']}"
            
            # Store the full group data in a separate, simpler format
            full_data_simple = []
            for group in groups_data:
                full_data_simple.append({
                    "num": group["number"],
                    "id": group["id"],
                    "title": group["title"],
                    "type": group["type"]
                })
            groups_dict["fulldata"] = full_data_simple
            
            # Add the selection instruction at the end
            groups_dict["group"] = "enter numbers to select (e.g., 1,2,4,6)"
            
            # Save to Firebase
            db.child("groups").set(groups_dict)
            print(f"\n🎉 Successfully saved {len(groups_data)} groups to Firebase!")
            print("\n📊 Groups list:")
            for group in groups_data:
                print(f"  {group['number']}. {group['title']} ({group['type']}) - ID: {group['id']}")
            print(f"\n💡 Now go to Firebase and enter group numbers in the 'group' field (e.g., 1,2,4,6)")
        else:
            print("❌ No groups found!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    print("🚀 Telegram Groups Refresher")
    print("=" * 30)
    asyncio.run(refresh_groups())
    print("\n✨ Done!") 