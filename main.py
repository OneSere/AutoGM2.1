import os
import time
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import pyrebase
from pytz import timezone
import random
import json

# --- Firebase Config ---
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

API_ID = 24384486
API_HASH = "ea089ed3d3e4b093939fa3eab6d062df"
PHONE = ""  # The phone number to login
FIREBASE_PROMOS_PATH = "promos"
FIREBASE_INTERVAL_PATH = "interval"
FIREBASE_STATUS_PATH = "live_status"
FIREBASE_OTP_PATH = "otp"
FIREBASE_SESSION_PATH = "session"
FIREBASE_USER_REPLIES_PATH = "user_replies"  # Track user replies
FIREBASE_GROUPS_PATH = "groups"  # Groups list and selection

# --- Helper Functions ---
def save_status(msg, level="INFO"):
    """Enhanced status logging with levels and better formatting"""
    now = datetime.utcnow().isoformat()
    ist_time = get_current_ist().strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Format message with timestamp and level
    formatted_msg = f"[{level}] {msg} | {ist_time}"
    
    db.child(FIREBASE_STATUS_PATH).push({
        "msg": formatted_msg, 
        "ts": now,
        "level": level,
        "ist_time": ist_time
    })
    
    # Delete old status messages (older than 1 hour)
    all_status = db.child(FIREBASE_STATUS_PATH).get().val() or {}
    cutoff = datetime.utcnow() - timedelta(hours=1)
    for key, val in all_status.items():
        try:
            ts = datetime.fromisoformat(val["ts"])
            if ts < cutoff:
                db.child(FIREBASE_STATUS_PATH).child(key).remove()
        except Exception:
            db.child(FIREBASE_STATUS_PATH).child(key).remove()

def save_groups_to_firebase(groups_data):
    """Save groups data to Firebase"""
    try:
        db.child(FIREBASE_GROUPS_PATH).set(groups_data)
        save_status(f"Saved {len(groups_data)} groups to Firebase", "SUCCESS")
        return True
    except Exception as e:
        save_status(f"Error saving groups to Firebase: {e}", "ERROR")
        return False

def load_groups_from_firebase():
    """Load groups data from Firebase"""
    try:
        groups_data = db.child(FIREBASE_GROUPS_PATH).get().val()
        if groups_data:
            save_status(f"Loaded {len(groups_data)} groups from Firebase", "INFO")
            return groups_data
        else:
            save_status("No saved groups found in Firebase", "WARNING")
            return []
    except Exception as e:
        save_status(f"Error loading groups from Firebase: {e}", "ERROR")
        return []

async def get_groups_from_folder(client, folder_name="123456"):
    """Get groups from a specific Telegram folder"""
    try:
        save_status(f"Fetching groups from Telegram folder: {folder_name}", "INFO")
        groups_data = []
        
        # Get all dialogs first
        all_dialogs = []
        async for dialog in client.iter_dialogs():
            all_dialogs.append(dialog)
        
        # Try to find the folder by name
        folder_entity = None
        for dialog in all_dialogs:
            if hasattr(dialog.entity, 'title') and dialog.entity.title == folder_name:
                folder_entity = dialog.entity
                break
        
        if folder_entity:
            save_status(f"Found folder: {folder_name}", "SUCCESS")
            
            # Get dialogs from this folder
            try:
                # For folders, we need to get the participants/members
                if hasattr(folder_entity, 'participants_count'):
                    # This is a folder, get its contents
                    async for dialog in client.iter_dialogs():
                        # Check if this dialog belongs to our folder
                        # We'll check by looking at the folder structure
                        if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                            # For now, let's get all groups and channels
                            # You can refine this logic based on your folder structure
                            group_info = {
                                "id": dialog.id,
                                "title": dialog.title,
                                "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                                "type": "group" if dialog.is_group else "channel",
                                "participants_count": getattr(dialog.entity, 'participants_count', 0)
                            }
                            groups_data.append(group_info)
                            save_status(f"Found group in folder: {dialog.title} (ID: {dialog.id})", "INFO")
                
                # Alternative approach: get all groups and assume they're in the folder
                # This is more reliable since folder access can be tricky
                if not groups_data:
                    save_status("Using alternative method: fetching all groups", "INFO")
                    async for dialog in client.iter_dialogs():
                        if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                            group_info = {
                                "id": dialog.id,
                                "title": dialog.title,
                                "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                                "type": "group" if dialog.is_group else "channel",
                                "participants_count": getattr(dialog.entity, 'participants_count', 0)
                            }
                            groups_data.append(group_info)
                            save_status(f"Found group: {dialog.title} (ID: {dialog.id})", "INFO")
                
            except Exception as e:
                save_status(f"Error accessing folder contents: {e}", "ERROR")
                # Fallback: get all groups
                async for dialog in client.iter_dialogs():
                    if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                        group_info = {
                            "id": dialog.id,
                            "title": dialog.title,
                            "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                            "type": "group" if dialog.is_group else "channel",
                            "participants_count": getattr(dialog.entity, 'participants_count', 0)
                        }
                        groups_data.append(group_info)
                        save_status(f"Found group (fallback): {dialog.title} (ID: {dialog.id})", "INFO")
        else:
            save_status(f"Folder '{folder_name}' not found, fetching all groups", "WARNING")
            # Fallback: get all groups if folder not found
            async for dialog in client.iter_dialogs():
                if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                    group_info = {
                        "id": dialog.id,
                        "title": dialog.title,
                        "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                        "type": "group" if dialog.is_group else "channel",
                        "participants_count": getattr(dialog.entity, 'participants_count', 0)
                    }
                    groups_data.append(group_info)
                    save_status(f"Found group: {dialog.title} (ID: {dialog.id})", "INFO")
        
        if groups_data:
            save_status(f"Successfully found {len(groups_data)} groups", "SUCCESS")
            return groups_data
        else:
            save_status("No groups found", "WARNING")
            return []
            
    except Exception as e:
        save_status(f"Error fetching groups from folder: {e}", "ERROR")
        return []

async def fetch_and_save_groups_list(client):
    """Fetch all groups from Telegram and save numbered list to Firebase"""
    try:
        save_status("Fetching all groups from Telegram...", "INFO")
        groups_data = []
        group_number = 1
        
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
                save_status(f"Found group {group_number}: {dialog.title} (ID: {dialog.id})", "INFO")
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
            db.child(FIREBASE_GROUPS_PATH).set(groups_dict)
            save_status(f"Successfully saved {len(groups_data)} groups to Firebase", "SUCCESS")
            save_status("Please select groups by entering numbers in Firebase group field", "INFO")
            return groups_data
        else:
            save_status("No groups found in Telegram", "WARNING")
            return []
            
    except Exception as e:
        save_status(f"Error fetching groups: {e}", "ERROR")
        return []

def get_selected_groups():
    """Get the selected groups from Firebase"""
    try:
        groups_data = db.child(FIREBASE_GROUPS_PATH).get().val()
        if not groups_data:
            return []
        
        # Get the selection from group field
        selection = groups_data.get("group", "")
        if not selection or selection == "enter numbers to select (e.g., 1,2,4,6)":
            return []
        
        # Parse the selection (e.g., "1,2,4,6")
        try:
            selected_numbers = [int(x.strip()) for x in selection.split(",") if x.strip().isdigit()]
        except:
            save_status("Invalid group selection format. Use numbers separated by commas (e.g., 1,2,4,6)", "ERROR")
            return []
        
        # Get the full group data
        full_data = groups_data.get("fulldata", [])
        if not full_data:
            save_status("Full group data not found, please refresh groups", "ERROR")
            return []
        
        # Get the selected groups with their actual IDs
        selected_groups = []
        for num in selected_numbers:
            for group in full_data:
                if group["num"] == num:
                    selected_groups.append({
                        "number": group["num"],
                        "id": group["id"],
                        "title": group["title"],
                        "type": group["type"]
                    })
                    break
        
        if selected_groups:
            save_status(f"Selected {len(selected_groups)} groups: {[g['number'] for g in selected_groups]}", "SUCCESS")
        else:
            save_status("No groups selected or invalid selection", "WARNING")
        
        return selected_groups
        
    except Exception as e:
        save_status(f"Error getting selected groups: {e}", "ERROR")
        return []

async def get_groups_list(client):
    """Get groups list - fetch from Telegram and allow manual selection"""
    # First check if groups are already saved
    existing_groups = db.child(FIREBASE_GROUPS_PATH).get().val()
    
    if not existing_groups:
        # No groups saved, fetch them
        save_status("No groups found in Firebase, fetching from Telegram...", "INFO")
        return await fetch_and_save_groups_list(client)
    else:
        # Groups are saved, check if selection is made
        selected_groups = get_selected_groups()
        if selected_groups:
            save_status(f"Using {len(selected_groups)} selected groups", "INFO")
            return selected_groups
        else:
            save_status("Groups found but none selected. Please select groups in Firebase", "WARNING")
            return []

def can_reply_to_user(user_id):
    """Check if we can reply to this user (once per 24 hours)"""
    try:
        user_replies = db.child(FIREBASE_USER_REPLIES_PATH).get().val() or {}
        user_id_str = str(user_id)
        
        if user_id_str not in user_replies:
            return True
        
        last_reply_time = user_replies[user_id_str]
        last_reply_dt = datetime.fromisoformat(last_reply_time)
        now = datetime.utcnow()
        
        # Check if 24 hours have passed
        if now - last_reply_dt >= timedelta(hours=24):
            return True
        
        return False
    except Exception as e:
        save_status(f"Error checking user reply status: {e}", "ERROR")
        return False

def mark_user_replied(user_id):
    """Mark that we've replied to this user"""
    try:
        user_id_str = str(user_id)
        now = datetime.utcnow().isoformat()
        db.child(FIREBASE_USER_REPLIES_PATH).child(user_id_str).set(now)
        
        # Clean up old user entries (older than 48 hours)
        user_replies = db.child(FIREBASE_USER_REPLIES_PATH).get().val() or {}
        cutoff = datetime.utcnow() - timedelta(hours=48)
        for uid, reply_time in user_replies.items():
            try:
                reply_dt = datetime.fromisoformat(reply_time)
                if reply_dt < cutoff:
                    db.child(FIREBASE_USER_REPLIES_PATH).child(uid).remove()
            except Exception:
                db.child(FIREBASE_USER_REPLIES_PATH).child(uid).remove()
    except Exception as e:
        save_status(f"Error marking user replied: {e}", "ERROR")

def get_promos():
    promos = db.child(FIREBASE_PROMOS_PATH).get().val()
    # Only use non-empty, non-whitespace promos
    if promos and isinstance(promos, list):
        return [p for p in promos if p and str(p).strip()]
    elif promos and isinstance(promos, dict):
        return [v for k, v in sorted(promos.items()) if v and str(v).strip()]
    return []

def get_interval():
    val = db.child(FIREBASE_INTERVAL_PATH).get().val()
    try:
        return int(val)
    except Exception:
        return 10  # default 10 minutes

def save_session(session_str):
    db.child(FIREBASE_SESSION_PATH).set(session_str)

def load_session():
    return db.child(FIREBASE_SESSION_PATH).get().val()

def get_otp_from_firebase():
    return db.child(FIREBASE_OTP_PATH).get().val()

def clear_otp_in_firebase():
    db.child(FIREBASE_OTP_PATH).remove()

# --- Humanize Delays ---
def get_current_ist():
    return datetime.now(timezone('Asia/Kolkata'))

def get_next_active_delay():
    now = get_current_ist()
    hour = now.hour
    minute = now.minute
    t = hour * 60 + minute
    # Define time slots in minutes since midnight
    slots = [
        (7*60, 11*60+30, 'active'),
        (11*60+30, 11*60+50, 'tea'),
        (11*60+50, 13*60+30, 'active'),
        (13*60+30, 14*60+30, 'lunch'),
        (14*60+30, 17*60, 'active'),
        (17*60, 17*60+20, 'tea'),
        (17*60+20, 25*60, 'active'),  # 25*60 = 1:00 AM next day
        (25*60, 29*60, 'active'),     # 1:00 AM – 5:00 AM
        (29*60, 33*60, 'sleep'),      # 5:00 AM – 9:00 AM (next day)
    ]
    # Adjust for after midnight
    if t < 7*60:
        t += 24*60
    for start, end, status in slots:
        if start <= t < end:
            if status == 'active':
                return 0, 'active'
            else:
                # Sleep until end of break
                mins_to_wait = end - t
                return mins_to_wait * 60, status
    # If not in any slot, sleep until 7:00 AM
    if t >= 25*60 and t < 29*60:
        mins_to_wait = 29*60 - t
        return mins_to_wait * 60, 'sleep'
    # Default: sleep until 7:00 AM
    mins_to_wait = (7*60 + 24*60) - t
    return mins_to_wait * 60, 'sleep'

# --- Telegram Login ---
async def telegram_login():
    session_str = load_session()
    if session_str:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                save_status("Auto-login successful using saved session", "SUCCESS")
                return client
            else:
                save_status("Session expired, clearing and doing fresh login", "WARNING")
                # Clear the invalid session
                try:
                    db.child(FIREBASE_SESSION_PATH).remove()
                    save_status("Cleared expired session from Firebase", "INFO")
                except:
                    pass
                await client.disconnect()
        except Exception as e:
            save_status(f"Session login failed: {e}", "WARNING")
            # Clear the invalid session
            try:
                db.child(FIREBASE_SESSION_PATH).remove()
                save_status("Cleared invalid session from Firebase", "INFO")
            except:
                pass
            await client.disconnect()
    
    # No session or session invalid, do fresh login
    save_status("Starting fresh login process", "INFO")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        await client.send_code_request(PHONE)
        # Explicitly create the /otp key in Firebase for you to paste the OTP
        db.child(FIREBASE_OTP_PATH).set("PASTE OTP HERE")
        save_status(f"OTP sent to {PHONE}. Waiting for OTP in Firebase...", "INFO")
        
        # Wait for OTP to appear in Firebase
        for _ in range(20):  # Wait up to 20*3=60 seconds
            otp = get_otp_from_firebase()
            if otp and otp != "PASTE OTP HERE":
                try:
                    await client.sign_in(PHONE, otp)
                    session_str = client.session.save()
                    save_session(session_str)
                    save_status("Login successful, session saved", "SUCCESS")
                    clear_otp_in_firebase()
                    return client
                except Exception as e:
                    save_status(f"OTP error: {e}", "ERROR")
                    clear_otp_in_firebase()
                    break
            await asyncio.sleep(3)
        
        save_status("OTP not found or invalid after 60 seconds", "ERROR")
        await client.disconnect()
        return None
    except Exception as e:
        save_status(f"Login error: {e}", "ERROR")
        await client.disconnect()
        return None

# --- Firebase Initialization ---
def ensure_firebase_defaults():
    # Promos
    promos = db.child(FIREBASE_PROMOS_PATH).get().val()
    default_promos = [
        "🔥 All-in-One Telegram Toolkit You Need\n\n💸 Zepto Refund Method – ₹99\nEasy-to-follow trick to get successful refunds quickly\n\n📨 24/7 Telegram Auto Message Sending Tool – ₹159\nKeep your messages going non-stop, even when you're offline\n\n🤖 Custom Telegram Bot Script – ₹300\nTailor-made scripts to automate any task on Telegram\n\n💬 DM @curiositymind | ✅ Escrow Safe | 💰 Negotiable | Warranty Included",
        "🚀 Tools to Grow, Automate & Save on Telegram\n\n👥 Telegram Group Scraping Tool – ₹49\nExtract members from any group with one click – fast & effective\n\n💸 100% Working Zepto Refund – ₹99\nReal method with high success rate and step-by-step guidance\n\n📡 Telegram Bot Hosting Method – ₹30/month\nRun your Telegram bots 24/7 without a VPS – light and stable\n\n📩 DM @curiositymind | Escrow ✅ | Nego Possible | Full Warranty",
        "💬 Boost Your Telegram Game Like a Pro\n\n📤 Auto Message Send Tool – ₹159\nSchedule or loop messages every few minutes across multiple groups\n\n💰 Zepto Refund Plan – ₹99\nWorking method with actual proof and support included\n\n🤖 Telegram Bot Script Making – ₹300\nGet any kind of bot logic built specifically for Telegram\n\n💬 DM @curiositymind | Escrow + Support ✅ | Flexible Pricing 💵 | Warranty Available",
        "🛠️ Tools for Telegram Hustlers & Automators\n\n🤖 Telegram Bot Script (Custom Build) – ₹300\nGet bots made for anything – replies, posts, data, filters & more\n\n📨 Auto Message Sender (24/7) – ₹159\nKeep your accounts active without lifting a finger\n\n👥 Group Member Scraper – ₹49\nFind and add targeted Telegram users with ease\n\nDM @curiositymind | Escrow Protected 🔐 | Price Negotiation ✅ | Warranty ✔",
        "📈 Work Smarter on Telegram – Not Harder\n\n💸 Real Zepto Refund Method – ₹99\nNo risky steps – just follow and get results\n\n📤 24/7 Telegram Message Bot – ₹159\nSend messages day and night, auto-managed by tool\n\n💻 Telegram Bot Hosting Method – ₹30/month\nAffordable and easy way to keep your bot online full-time\n\n💬 DM @curiositymind | Nego ✅ | Escrow Supported | With Warranty 🛠️",
        "💻 Professional Telegram Tools, Minimal Prices\n\n🛠️ Telegram Bot Script Development – ₹300\nYour logic, our code – smart Telegram bots built on demand\n\n📨 Auto Telegram Messaging Tool – ₹159\nSaves time, boosts reach – messages go on loop, 24/7\n\n📥 Telegram Group Scraper – ₹49\nGet fresh users from any group, in just seconds\n\nDM @curiositymind | Escrow On | Price Chat Open 💬 | Warranty ✅",
        "🔧 Tools to Manage, Automate & Scale Telegram\n\n📤 Auto Message Sender Tool – ₹159\nSet and forget – this bot handles the spamming for you safely\n\n💰 Zepto Refund Method – ₹99\nWorking plan to get your cashback hassle-free\n\n📡 Telegram Bot Hosting Method – ₹30/Month\nKeep your custom bots running without paying for servers\n\n💬 DM @curiositymind | Escrow & Nego ✅ | Warranty Support Available",
        "🧠 Made for Smart Telegram Users\n\n👥 Group Scraping Tool – ₹49\nQuickly fetch members from any public group with one click\n\n🤖 Custom Telegram Bot Script – ₹300\nWe build bots that follow your instructions perfectly\n\n📨 Auto Message Send Tool (24x7) – ₹159\nStay live even while you sleep – send messages non-stop\n\nDM @curiositymind for access | Escrow ✅ | Negotiable | Warranty Assured",
        "💬 Start Saving Time & Earning More on Telegram\n\n💸 Zepto Refund Plan – ₹99\nEasy method with working results and full guidance\n\n📨 Auto Telegram Messaging Bot – ₹159\nSends your message across multiple groups on full loop\n\n💻 Telegram Bot Hosting Method – ₹30/month\nRun your Telegram bots without expensive servers or coding\n\n💬 DM @curiositymind | Escrow ✅ | Open to Nego 💰 | Warranty ✅"
    ]
    if not promos:
        db.child(FIREBASE_PROMOS_PATH).set(default_promos)
    
    # Interval
    interval = db.child(FIREBASE_INTERVAL_PATH).get().val()
    if not interval or str(interval).strip() == "":
        db.child(FIREBASE_INTERVAL_PATH).set(10)
    
    # Live status
    live_status = db.child(FIREBASE_STATUS_PATH).get().val()
    if not live_status:
        now = datetime.utcnow().isoformat()
        db.child(FIREBASE_STATUS_PATH).push({"msg": "[INIT] Bot started. Waiting for login.", "ts": now})
    
    # Start/Stop system
    startstop = db.child("startstopsystem").get().val()
    if startstop is None:
        db.child("startstopsystem").set("")
    
    # OTP
    otp = db.child(FIREBASE_OTP_PATH).get().val()
    if otp is None:
        db.child(FIREBASE_OTP_PATH).set("")
    
    # Session
    session = db.child(FIREBASE_SESSION_PATH).get().val()
    if session is None:
        db.child(FIREBASE_SESSION_PATH).set("")
    
    # User replies tracking
    user_replies = db.child(FIREBASE_USER_REPLIES_PATH).get().val()
    if user_replies is None:
        db.child(FIREBASE_USER_REPLIES_PATH).set({})
    
    # Groups
    groups = db.child(FIREBASE_GROUPS_PATH).get().val()
    if groups is None:
        db.child(FIREBASE_GROUPS_PATH).set({})

ADMIN_NOTE = ("📢 Note from Admin \n"
              "Hey dosto! This is just an advertising/demo account.\n"
              "Ye account sirf promotion ke liye use ho raha hai.\n\n"
              "👉 For any real tasks, queries, or services, kindly contact: @curiositymind on telegram \n\n"
              "📋 This account was officially purchased on 25th June / यह अकाउंट 25 जून को खरीदा गया था।")

async def handle_incoming_messages(client):
    @client.on(events.NewMessage(incoming=True, outgoing=False))
    async def handler(event):
        try:
            # Only reply to private users, not groups or channels
            if event.is_private:
                user_id = event.sender_id
                if can_reply_to_user(user_id):
                    await asyncio.sleep(5)
                    await event.reply(ADMIN_NOTE)
                    mark_user_replied(user_id)
                    save_status(f"Sent admin note to user {user_id} (first time in 24h)", "INFO")
                else:
                    save_status(f"Skipped reply to user {user_id} (already replied in last 24h)", "INFO")
        except Exception as e:
            save_status(f"Auto-reply error: {e}", "ERROR")

def should_stop():
    val = db.child('startstopsystem').get().val()
    return val and str(val).strip().upper() == 'STOP'

async def wait_until_start():
    while True:
        startstop = db.child("startstopsystem").get().val()
        if not startstop or str(startstop).strip().upper() != "STOP":
            save_status("STOP command cleared. Resuming message sending", "SUCCESS")
            break
        save_status("STOP command active. Waiting for resume...", "PAUSED")
        await asyncio.sleep(10)

async def health_check(client):
    """Perform a health check on the client connection"""
    try:
        if not client.is_connected():
            return False
        
        # Try to get account info to test authorization
        me = await client.get_me()
        if me:
            save_status(f"Health check passed - Connected as {me.first_name}", "INFO")
            return True
        else:
            save_status("Health check failed - Could not get account info", "ERROR")
            return False
    except Exception as e:
        save_status(f"Health check failed: {e}", "ERROR")
        return False

async def ensure_client_connected(client):
    """Ensure client is connected and handle reconnection"""
    try:
        if not client.is_connected():
            save_status("Client disconnected, attempting reconnection...", "WARNING")
            await client.connect()
            if await client.is_user_authorized():
                # Perform health check
                if await health_check(client):
                    save_status("Reconnection successful", "SUCCESS")
                    return True
                else:
                    save_status("Reconnection failed - health check failed", "ERROR")
                    return False
            else:
                save_status("Reconnection failed - session expired, will force fresh login", "ERROR")
                # Clear the invalid session
                try:
                    db.child(FIREBASE_SESSION_PATH).remove()
                    save_status("Cleared invalid session from Firebase", "INFO")
                except:
                    pass
                return False
        else:
            # Client is connected, perform health check
            if await health_check(client):
                return True
            else:
                save_status("Connected but health check failed", "ERROR")
                return False
    except Exception as e:
        save_status(f"Connection check failed: {e}", "ERROR")
        return False

# --- Main Message Sending Loop ---
async def main_loop():
    last_sent_promo = {}  # group_id -> last promo index sent
    consecutive_auth_failures = 0  # Track consecutive auth failures
    consecutive_connection_failures = 0  # Track connection failures
    group_idx = 0  # Track which group to message next
    promo_idx = 0  # Track which promo to send next
    
    while True:
        try:
            client = await telegram_login()
            if not client:
                consecutive_auth_failures += 1
                if consecutive_auth_failures >= 3:
                    save_status("Multiple login failures. Clearing session and waiting 10 minutes", "ERROR")
                    try:
                        db.child(FIREBASE_SESSION_PATH).remove()
                    except:
                        pass
                    consecutive_auth_failures = 0
                    consecutive_connection_failures = 0
                    await asyncio.sleep(600)  # Wait 10 minutes
                else:
                    save_status(f"Could not login. Retrying in 5 minutes (attempt {consecutive_auth_failures})", "ERROR")
                    await asyncio.sleep(300)  # Wait 5 minutes
                continue
            
            # Reset failure counters on successful login
            consecutive_auth_failures = 0
            consecutive_connection_failures = 0
            
            # Test connection immediately after login
            if not await ensure_client_connected(client):
                save_status("Initial connection test failed, restarting login process", "ERROR")
                consecutive_connection_failures += 1
                if consecutive_connection_failures >= 2:
                    save_status("Multiple connection failures. Waiting 10 minutes before retry", "ERROR")
                    await asyncio.sleep(600)
                    consecutive_connection_failures = 0
                continue
            
            # Start message handler
            await handle_incoming_messages(client)
            
            # Get groups list (from Telegram folder)
            groups_data = await get_groups_list(client)
            
            if not groups_data:
                save_status("No groups available. Sleeping 10 min", "WARNING")
                await client.disconnect()
                await asyncio.sleep(600)
                continue
            
            promos = get_promos()
            if not promos:
                save_status("No promos found in Firebase. Sleeping 10 min", "WARNING")
                await client.disconnect()
                await asyncio.sleep(600)
                continue
            
            group_list = groups_data
            promo_list = promos
            group_count = len(group_list)
            promo_count = len(promo_list)
            
            save_status(f"Starting message loop with {group_count} groups and {promo_count} promos", "INFO")
            
            while True:
                # Always check start/stop system before sending
                startstop = db.child("startstopsystem").get().val()
                if startstop and str(startstop).strip().upper() == "STOP":
                    jitter = random.randint(5, 30)
                    save_status(f"STOP command active. Waiting {jitter}s before checking again", "PAUSED")
                    await asyncio.sleep(jitter)
                    await wait_until_start()
                    jitter = random.randint(5, 30)
                    save_status(f"STOP cleared. Waiting {jitter}s before resuming", "SUCCESS")
                    await asyncio.sleep(jitter)
                
                # Check if in break or active slot
                delay, status = get_next_active_delay()
                if status != 'active':
                    save_status(f"{status.title()} Break: resting {delay//60} min", "PAUSED")
                    await asyncio.sleep(delay)
                    jitter = random.randint(1, 5)
                    save_status(f"Post-break random delay: {jitter}s", "INFO")
                    await asyncio.sleep(jitter)
                    
                    # After break, check start/stop again
                    startstop = db.child("startstopsystem").get().val()
                    if startstop and str(startstop).strip().upper() == "STOP":
                        jitter = random.randint(5, 30)
                        save_status(f"STOP command active after break. Waiting {jitter}s", "PAUSED")
                        await asyncio.sleep(jitter)
                        await wait_until_start()
                        jitter = random.randint(5, 30)
                        save_status(f"STOP cleared after break. Waiting {jitter}s", "SUCCESS")
                        await asyncio.sleep(jitter)
                        continue
                
                # Ensure client is connected before sending
                if not await ensure_client_connected(client):
                    save_status("Client connection failed, restarting main loop", "ERROR")
                    consecutive_connection_failures += 1
                    if consecutive_connection_failures >= 3:
                        save_status("Multiple connection failures. Waiting 15 minutes before retry", "ERROR")
                        await asyncio.sleep(900)  # Wait 15 minutes
                        consecutive_connection_failures = 0
                    break
                
                interval = get_interval()
                # Send to one group per interval, round-robin
                group_info = group_list[group_idx % group_count]
                promo = promo_list[promo_idx % promo_count]
                gid = str(group_info["id"])
                try:
                    jitter = random.randint(5, 15)
                    save_status(f"Waiting {jitter}s before sending to {group_info['title']} ({group_info['id']})", "INFO")
                    await asyncio.sleep(jitter)
                    
                    # Send message using group ID
                    await client.send_message(int(group_info["id"]), promo)
                    save_status(f"✅ Sent promo {promo_idx+1} to {group_info['title']} ({group_info['id']})", "SUCCESS")
                    last_sent_promo[gid] = promo_idx
                    
                    jitter2 = random.randint(5, 15)
                    save_status(f"Waiting {jitter2}s after sending to {group_info['title']}", "INFO")
                    await asyncio.sleep(jitter2)
                except Exception as e:
                    save_status(f"❌ Error sending to {group_info['title']}: {e}", "ERROR")
                    # If it's an authorization error, break the loop to force re-login
                    if "authorized" in str(e).lower() or "session" in str(e).lower():
                        save_status("Authorization error detected, forcing fresh login", "ERROR")
                        try:
                            db.child(FIREBASE_SESSION_PATH).remove()
                            save_status("Cleared invalid session", "INFO")
                        except:
                            pass
                        break
                    # If it's a disconnection error, try to reconnect
                    elif "disconnected" in str(e).lower():
                        save_status("Detected disconnection, attempting reconnection", "WARNING")
                        if not await ensure_client_connected(client):
                            save_status("Reconnection failed, restarting main loop", "ERROR")
                            consecutive_connection_failures += 1
                    break
                # Move to next group and promo for next interval
                group_idx = (group_idx + 1) % group_count
                promo_idx = (promo_idx + 1) % promo_count
                # Wait interval before next message
                real_interval = max(1, interval * 60)
                save_status(f"⏰ Waiting {real_interval//60}m {real_interval%60}s before next message", "INFO")
                await asyncio.sleep(real_interval)
        except Exception as e:
            save_status(f"Main loop error: {e}", "ERROR")
            # If it's an authorization error, clear session
            if "authorized" in str(e).lower() or "session" in str(e).lower():
                try:
                    db.child(FIREBASE_SESSION_PATH).remove()
                    save_status("Cleared invalid session due to error", "INFO")
                except:
                    pass
            consecutive_connection_failures += 1
            if consecutive_connection_failures >= 5:
                save_status("Too many consecutive failures. Waiting 20 minutes before retry", "ERROR")
                await asyncio.sleep(1200)  # Wait 20 minutes
                consecutive_connection_failures = 0
            else:
                await asyncio.sleep(120)  # Wait 2 minutes
        finally:
            try:
                await client.disconnect()
            except:
                pass
            await asyncio.sleep(30)  # Wait 30 seconds before next attempt

if __name__ == "__main__":
    ensure_firebase_defaults()
    asyncio.run(main_loop())
