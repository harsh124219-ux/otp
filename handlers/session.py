from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    FloodWait, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PasswordHashInvalid
)
from info import ADMIN_ID, API_ID, API_HASH
from database import get_config, add_account, accounts_col
import asyncio
from datetime import datetime

session_states = {}


# ── /login command ───────────────────────────────────────────────────────────

async def login_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply_text(
        "📱 **Step 1/5 — Phone Number**\n\n"
        "Enter the phone number with country code:\n"
        "_(e.g. +919876543210)_"
    )
    session_states[message.from_user.id] = {"step": "waiting_phone"}


# ── Message handler for login flow ──────────────────────────────────────────

async def handle_session_message(client: Client, message: Message):
    admin_id = message.from_user.id
    state = session_states.get(admin_id)
    if not state:
        return

    step = state.get("step")

    # ── STEP 1: Phone ─────────────────────────────────────────────────────────
    if step == "waiting_phone":
        phone = message.text.strip()
        temp_client = Client(
            "temp_session", api_id=API_ID, api_hash=API_HASH, in_memory=True
        )
        try:
            await temp_client.connect()
            code_info = await temp_client.send_code(phone)
            session_states[admin_id] = {
                "step": "waiting_code",
                "phone": phone,
                "phone_code_hash": code_info.phone_code_hash,
                "temp_client": temp_client,
                "account_password": "",   # will be set if 2FA exists
            }
            await message.reply_text(
                f"✅ OTP sent to `{phone}`.\n\n"
                "📱 **Step 2/5 — OTP Code**\n\n"
                "Enter the OTP you received:"
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_text(
                f"⚠️ Telegram says wait **{e.value}s**. Try again."
            )
            session_states.pop(admin_id, None)
        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")
            session_states.pop(admin_id, None)

    # ── STEP 2: OTP ───────────────────────────────────────────────────────────
    elif step == "waiting_code":
        code = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        phone_code_hash = state["phone_code_hash"]
        try:
            await temp_client.sign_in(phone, phone_code_hash, code)
            session_states[admin_id]["step"] = "waiting_country"
            await message.reply_text(
                "✅ Signed in!\n\n"
                "🌍 **Step 3/5 — Country**\n\n"
                "Enter country name for this account pool:\n_(e.g. India)_"
            )
        except SessionPasswordNeeded:
            session_states[admin_id]["step"] = "waiting_password"
            await message.reply_text(
                "🔐 **2FA Required**\n\n"
                "This account has Two-Step Verification.\n"
                "Enter the current 2FA password:"
            )
        except (PhoneCodeInvalid, PhoneCodeExpired):
            await message.reply_text(
                "❌ Invalid or expired OTP.\n"
                "Please start over with /login."
            )
            session_states.pop(admin_id, None)
        except Exception as e:
            await _notify_failure(client, admin_id, state.get("phone", "?"), str(e))
            session_states.pop(admin_id, None)

    # ── STEP 2b: Existing 2FA password (to sign in) ───────────────────────────
    elif step == "waiting_password":
        password = message.text.strip()
        temp_client = state["temp_client"]
        try:
            await temp_client.check_password(password)
            # Store the existing password — we'll need it if we want to change it
            session_states[admin_id]["account_password"] = password
            session_states[admin_id]["step"] = "waiting_country"
            await message.reply_text(
                "✅ 2FA verified!\n\n"
                "🌍 **Step 3/5 — Country**\n\n"
                "Enter country name for this account pool:\n_(e.g. India)_"
            )
        except PasswordHashInvalid:
            await message.reply_text("❌ Wrong password. Try again:")
        except Exception as e:
            await _notify_failure(client, admin_id, state.get("phone", "?"), str(e))
            session_states.pop(admin_id, None)

    # ── STEP 3: Country ───────────────────────────────────────────────────────
    elif step == "waiting_country":
        country = message.text.strip().upper()
        session_states[admin_id].update({"step": "waiting_price", "country": country})
        await message.reply_text(
            f"✅ Country: `{country}`\n\n"
            "💰 **Step 4/5 — Price**\n\n"
            "Enter the selling price for this account:\n_(e.g. 150)_"
        )

    # ── STEP 4: Price ─────────────────────────────────────────────────────────
    elif step == "waiting_price":
        try:
            price = float(message.text.strip())
            session_states[admin_id]["price"] = price
            # Show automation choices
            await _ask_automation_choices(
                client, admin_id, state["temp_client"], state["phone"]
            )
        except ValueError:
            await message.reply_text("❌ Invalid price. Enter a number like `150`:")

    # ── STEP 5a: Recovery email (prompted if not in DB) ──────────────────────
    elif step == "waiting_recovery_email":
        from database import update_config
        email = message.text.strip()
        update_config("recovery_email", email)
        session_states[admin_id]["recovery_email_override"] = email
        await message.reply_text(f"✅ Recovery email set to `{email}`. Running automation...")
        await _process_automation(
            client, admin_id,
            state["temp_client"], state["phone"],
            state["choices"]
        )

    # ── STEP 5b: New 2FA password (prompted if not in DB) ────────────────────
    elif step == "waiting_new_2fa":
        from database import update_config
        new_pwd = message.text.strip()
        update_config("admin_2fa", new_pwd)
        session_states[admin_id]["new_2fa_override"] = new_pwd
        await message.reply_text(f"✅ New 2FA password saved as `{new_pwd}`. Running automation...")
        await _process_automation(
            client, admin_id,
            state["temp_client"], state["phone"],
            state["choices"]
        )


# ── Automation menu (callback) ───────────────────────────────────────────────

async def _ask_automation_choices(
    bot: Client, admin_id: int, user_client: Client, phone: str
):
    session_states[admin_id]["step"] = "waiting_menu_choice"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚙️ Full Setup (Clear chats, block users, set 2FA + email)",
            callback_data="setup_all"
        )],
        [InlineKeyboardButton(
            "🧹 Clean Only (Clear group chats + block private contacts)",
            callback_data="setup_clean"
        )],
        [InlineKeyboardButton(
            "🛡️ Security Only (Change 2FA password + set recovery email)",
            callback_data="setup_sec"
        )],
        [InlineKeyboardButton(
            "⏩ Skip — Add directly to shop",
            callback_data="setup_skip"
        )],
    ])
    await bot.send_message(
        admin_id,
        f"✅ **Step 5/5 — Automation**\n\n"
        f"Account `{phone}` ready. Select setup type:",
        reply_markup=keyboard,
    )


async def handle_automation_callback(bot: Client, callback: CallbackQuery):
    admin_id = callback.from_user.id
    state = session_states.get(admin_id)

    if not state or state.get("step") != "waiting_menu_choice":
        await callback.answer("❌ Session expired. Start over with /login.", show_alert=True)
        return

    await callback.answer("Processing...")
    data = callback.data

    choices = {
        "clear_groups":    data in ["setup_all", "setup_clean"],
        "block_contacts":  data in ["setup_all", "setup_clean"],
        "change_2fa":      data in ["setup_all", "setup_sec"],
        "set_email":       data in ["setup_all", "setup_sec"],
    }

    try:
        await callback.message.delete()
    except Exception:
        pass

    # setup_skip → just save to DB, no automation
    if data == "setup_skip":
        await _save_account_to_db(bot, admin_id, state)
        return

    session_states[admin_id]["choices"] = choices
    await _process_automation(
        bot, admin_id,
        state["temp_client"], state["phone"],
        choices
    )


# ── Core automation logic ────────────────────────────────────────────────────

async def _process_automation(
    bot: Client, admin_id: int,
    user_client: Client, phone: str, choices: dict
):
    state = session_states.get(admin_id)
    config = get_config()

    # Determine new 2FA password
    new_2fa = (
        state.get("new_2fa_override")
        or config.get("admin_2fa")
        or "@OTPocean"
    )
    # Determine recovery email
    recovery_email = (
        state.get("recovery_email_override")
        or config.get("recovery_email")
    )

    # --- Gate: if security changes needed but email missing, ask for it first
    if choices.get("set_email") and not recovery_email:
        session_states[admin_id].update({
            "step": "waiting_recovery_email",
            "choices": choices
        })
        await bot.send_message(
            admin_id,
            "📧 **Recovery email not set.**\n\n"
            "Enter the recovery email to attach to this account:"
        )
        return

    # --- Gate: if 2FA change needed but new password missing, ask for it first
    if choices.get("change_2fa") and not new_2fa:
        session_states[admin_id].update({
            "step": "waiting_new_2fa",
            "choices": choices
        })
        await bot.send_message(
            admin_id,
            "🔐 **New 2FA password not configured.**\n\n"
            "Enter the new 2FA password to set on this account:"
        )
        return

    status_msg = await bot.send_message(
        admin_id, "⚙️ **Running automation...**"
    )

    result_lines = []
    final_password = state.get("account_password", "")

    try:
        # ── 1. Clear group/channel memberships ───────────────────────────────
        if choices.get("clear_groups"):
            left = 0
            try:
                async for dialog in user_client.get_dialogs():
                    chat = dialog.chat
                    if chat and chat.type in (
                        enums.ChatType.GROUP,
                        enums.ChatType.SUPERGROUP,
                        enums.ChatType.CHANNEL,
                    ):
                        try:
                            await user_client.leave_chat(chat.id, delete=True)
                            left += 1
                            await asyncio.sleep(0.3)   # avoid flood
                        except Exception:
                            pass
                result_lines.append(f"✅ Left {left} groups/channels")
            except Exception as e:
                result_lines.append(f"⚠️ Group cleanup error: {e}")

        # ── 2. Block private contacts & clear their chat history ─────────────
        if choices.get("block_contacts"):
            blocked = 0
            try:
                async for dialog in user_client.get_dialogs():
                    chat = dialog.chat
                    if chat and chat.type in (
                        enums.ChatType.PRIVATE,
                        enums.ChatType.BOT,
                    ):
                        if chat.id == 777000:   # never block Telegram service account
                            continue
                        try:
                            # delete_chat_history(chat_id, revoke=True) deletes for both sides
                            await user_client.delete_chat_history(chat.id, revoke=True)
                            await user_client.block_user(chat.id)
                            blocked += 1
                            await asyncio.sleep(0.3)
                        except Exception:
                            pass
                result_lines.append(f"✅ Blocked {blocked} contacts & cleared history")
            except Exception as e:
                result_lines.append(f"⚠️ Block contacts error: {e}")

        # ── 3. 2FA password change / enable ──────────────────────────────────
        if choices.get("change_2fa"):
            try:
                hint = "Hind Deals"
                existing_pwd = state.get("account_password", "")

                if existing_pwd:
                    # Account already HAS 2FA — change it
                    await user_client.change_cloud_password(
                        current_password=existing_pwd,
                        new_password=new_2fa,
                        new_hint=hint,
                    )
                    result_lines.append(f"✅ 2FA changed to `{new_2fa}`")
                else:
                    # Account has NO 2FA — enable it
                    # enable_cloud_password supports email param directly
                    email_arg = recovery_email if choices.get("set_email") else None
                    await user_client.enable_cloud_password(
                        password=new_2fa,
                        hint=hint,
                        email=email_arg,
                    )
                    result_lines.append(f"✅ 2FA enabled: `{new_2fa}`")
                    if email_arg:
                        result_lines.append(f"✅ Recovery email set: `{email_arg}`")
                        choices["set_email"] = False  # already done inside enable_cloud_password

                final_password = new_2fa
            except Exception as e:
                result_lines.append(f"⚠️ 2FA error: {e}")

        # ── 4. Set recovery email (if not already done with 2FA enable) ──────
        if choices.get("set_email") and recovery_email:
            # Can only set email via enable_cloud_password or change_cloud_password
            # If we already set it above, this is skipped.
            # If account already had 2FA and we changed it, email must be set via
            # change_cloud_password → but change_cloud_password has no email param.
            # Workaround: if we can, disable and re-enable with email.
            try:
                current_pwd = final_password or state.get("account_password", "")
                if current_pwd:
                    await user_client.remove_cloud_password(current_pwd)
                    await user_client.enable_cloud_password(
                        password=current_pwd,
                        hint="Hind Deals",
                        email=recovery_email,
                    )
                    result_lines.append(f"✅ Recovery email set: `{recovery_email}`")
                else:
                    result_lines.append("⚠️ Skipped email: no active 2FA password to re-enable with")
            except Exception as e:
                result_lines.append(f"⚠️ Email set error: {e}")

    except Exception as e:
        result_lines.append(f"❌ Unexpected automation error: {e}")

    # ── Save account to DB ────────────────────────────────────────────────────
    try:
        session_string = await user_client.export_session_string()
        await user_client.disconnect()
    except Exception as e:
        result_lines.append(f"⚠️ Session export error: {e}")
        session_string = None

    if session_string:
        country = state.get("country", "GLOBAL")
        price = state.get("price", 0.0)
        accounts_col.insert_one({
            "phone": phone,
            "session_string": session_string,
            "country": country,
            "price": price,
            "status": "available",
            "password": final_password,
            "added_at": datetime.utcnow(),
        })
        result_lines.append(f"✅ Saved to DB → Pool: {country}, Price: ₹{price}")
        result_lines.append(f"🔐 Stored 2FA: `{final_password or 'None'}`")
    else:
        result_lines.append("❌ Account NOT saved — session string export failed")

    summary = "\n".join(result_lines)
    try:
        await status_msg.edit_text(
            f"🎉 **Automation Complete for** `{phone}`\n\n{summary}"
        )
    except Exception:
        await bot.send_message(
            admin_id,
            f"🎉 **Automation Complete for** `{phone}`\n\n{summary}"
        )

    session_states.pop(admin_id, None)


async def _save_account_to_db(bot: Client, admin_id: int, state: dict):
    """Skips automation, just exports session and saves."""
    phone = state["phone"]
    temp_client = state["temp_client"]
    country = state.get("country", "GLOBAL")
    price = state.get("price", 0.0)
    account_password = state.get("account_password", "")

    try:
        session_string = await temp_client.export_session_string()
        await temp_client.disconnect()

        accounts_col.insert_one({
            "phone": phone,
            "session_string": session_string,
            "country": country,
            "price": price,
            "status": "available",
            "password": account_password,
            "added_at": datetime.utcnow(),
        })
        await bot.send_message(
            admin_id,
            f"✅ **Account added (no automation)**\n\n"
            f"📱 Phone: `{phone}`\n"
            f"🌍 Country: {country}\n"
            f"💰 Price: ₹{price}\n"
            f"🔐 2FA: `{account_password or 'Not set'}`"
        )
    except Exception as e:
        await bot.send_message(admin_id, f"❌ Failed to save account: `{e}`")

    session_states.pop(admin_id, None)


async def _notify_failure(bot: Client, admin_id: int, phone: str, error: str):
    await bot.send_message(
        admin_id,
        f"❌ **Login failed for** `{phone}`\n\nError: `{error}`\n\nRestart with /login."
    )
