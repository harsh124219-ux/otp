from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired, SessionPasswordNeeded
from info import ADMIN_ID, API_ID, API_HASH
from database import save_session, delete_session
import asyncio

# Admin states for session creation
# {admin_id: {"step": "phone", "phone": "...", "phone_code_hash": "..."}}
session_states = {}

async def login_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.reply_text("📱 Please enter the **phone number** (with country code, e.g., +919876543210):")
    session_states[message.from_user.id] = {"step": "waiting_phone"}

async def handle_session_message(client: Client, message: Message):
    admin_id = message.from_user.id
    state = session_states.get(admin_id)
    
    if not state:
        return

    step = state.get("step")

    if step == "waiting_phone":
        phone = message.text.strip()
        temp_client = Client("temp_session", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        try:
            await temp_client.connect()
            code_info = await temp_client.send_code(phone)
            session_states[admin_id] = {
                "step": "waiting_code",
                "phone": phone,
                "phone_code_hash": code_info.phone_code_hash,
                "temp_client": temp_client
            }
            await message.reply_text(f"✅ Code sent to {phone}. Please enter the OTP:")
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_text(f"⚠️ FloodWait: Please wait {e.value} seconds.")
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            session_states.pop(admin_id, None)

    elif step == "waiting_code":
        code = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        phone_code_hash = state["phone_code_hash"]

        try:
            await temp_client.sign_in(phone, phone_code_hash, code)
            session_string = await temp_client.export_session_string()
            save_session(session_string)
            await message.reply_text("✅ Session created and saved successfully!")
            await temp_client.disconnect()
            session_states.pop(admin_id, None)
        except SessionPasswordNeeded:
            session_states[admin_id]["step"] = "waiting_password"
            await message.reply_text("🔐 Two-step verification enabled. Please enter your password:")
        except (PhoneCodeInvalid, PhoneCodeExpired):
            await message.reply_text("❌ Invalid or expired code. Please try again or restart with /login.")
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            session_states.pop(admin_id, None)

    elif step == "waiting_password":
        password = message.text.strip()
        temp_client = state["temp_client"]

        try:
            await temp_client.check_password(password)
            session_string = await temp_client.export_session_string()
            save_session(session_string)
            await message.reply_text("✅ Session created and saved successfully!")
            await temp_client.disconnect()
            session_states.pop(admin_id, None)
        except Exception as e:
            await message.reply_text(f"❌ Password error: {str(e)}")
            session_states.pop(admin_id, None)

async def logout_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    delete_session()
    await message.reply_text("✅ Session deleted.")
