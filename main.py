import os
import time
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import pyrebase
from pytz import timezone
import random

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

API_ID = 25843334
API_HASH = "e752bb9ebc151b7e36741d7ead8e4fd0"
PHONE = "+919351044618"  # The phone number to login
FIREBASE_PROMOS_PATH = "promos"
FIREBASE_INTERVAL_PATH = "interval"
FIREBASE_STATUS_PATH = "live_status"
FIREBASE_OTP_PATH = "otp"
FIREBASE_SESSION_PATH = "session"
FIREBASE_USER_REPLIES_PATH = "user_replies"  # Track user replies

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
            await client.disconnect()
        except Exception as e:
            save_status(f"Session login failed: {e}", "WARNING")
            await client.disconnect()
    
    # No session, do fresh login
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

async def ensure_client_connected(client):
    """Ensure client is connected and handle reconnection"""
    try:
        if not client.is_connected():
            save_status("Client disconnected, attempting reconnection...", "WARNING")
            await client.connect()
            if await client.is_user_authorized():
                save_status("Reconnection successful", "SUCCESS")
                return True
            else:
                save_status("Reconnection failed - not authorized", "ERROR")
                return False
        return True
    except Exception as e:
        save_status(f"Connection check failed: {e}", "ERROR")
        return False

# --- Main Message Sending Loop ---
async def main_loop():
    last_sent_promo = {}  # group_id -> last promo index sent
    while True:
        client = await telegram_login()
        if not client:
            save_status("Could not login. Retrying in 2 minutes", "ERROR")
            await asyncio.sleep(120)
            continue
        
        try:
            # Start message handler
            await handle_incoming_messages(client)
            
            # Get dialogs
            dialogs = []
            async for dialog in client.iter_dialogs():
                # Only include groups and channels, never personal users
                if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
                    dialogs.append(dialog)
            
            if not dialogs:
                save_status("No groups/channels found. Sleeping 10 min", "WARNING")
                await client.disconnect()
                await asyncio.sleep(600)
                continue
            
            promos = get_promos()
            if not promos:
                save_status("No promos found in Firebase. Sleeping 10 min", "WARNING")
                await client.disconnect()
                await asyncio.sleep(600)
                continue
            
            group_list = dialogs
            promo_list = promos
            idx = 0
            
            save_status(f"Starting message loop with {len(group_list)} groups and {len(promo_list)} promos", "INFO")
            
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
                    break
                
                interval = get_interval()
                group = group_list[idx % len(group_list)]
                gid = str(group.id)
                
                # Select promo for this group, not repeating last promo if possible
                last_idx = last_sent_promo.get(gid, -1)
                available_indices = [i for i in range(len(promo_list)) if i != last_idx]
                if not available_indices:
                    available_indices = list(range(len(promo_list)))
                promo_idx = available_indices[idx % len(available_indices)]
                promo = promo_list[promo_idx]
                
                try:
                    jitter = random.randint(5, 15)
                    save_status(f"Waiting {jitter}s before sending to {group.title} ({group.id})", "INFO")
                    await asyncio.sleep(jitter)
                    
                    await client.send_message(group, promo)
                    save_status(f"✅ Sent promo {promo_idx+1} to {group.title} ({group.id})", "SUCCESS")
                    last_sent_promo[gid] = promo_idx
                    
                    jitter2 = random.randint(5, 15)
                    save_status(f"Waiting {jitter2}s after sending to {group.title}", "INFO")
                    await asyncio.sleep(jitter2)
                    
                except Exception as e:
                    save_status(f"❌ Error sending to {group.title}: {e}", "ERROR")
                    # If it's a disconnection error, try to reconnect
                    if "disconnected" in str(e).lower():
                        save_status("Detected disconnection, attempting reconnection", "WARNING")
                        if not await ensure_client_connected(client):
                            save_status("Reconnection failed, restarting main loop", "ERROR")
                            break
                
                idx += 1
                # Strict interval: wait exactly interval minutes (no jitter)
                real_interval = max(1, interval * 60)
                save_status(f"⏰ Waiting {real_interval//60}m {real_interval%60}s before next message", "INFO")
                await asyncio.sleep(real_interval)
                
        except Exception as e:
            save_status(f"Main loop error: {e}", "ERROR")
            await asyncio.sleep(60)
        finally:
            try:
                await client.disconnect()
            except:
                pass
            await asyncio.sleep(10)

if __name__ == "__main__":
    ensure_firebase_defaults()
    asyncio.run(main_loop())
