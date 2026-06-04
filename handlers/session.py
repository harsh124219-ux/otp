"""
handlers/session.py
───────────────────
Admin /login flow:
  Step 1  — Phone number
  Step 2  — OTP from Telegram
  Step 2b — 2FA password (if account already has one)
  Step 3  — Country pool name
  Step 4  — Selling price
  Step 5  — Choose automation level (inline keyboard)
  Step 6  — (if set_email) Enter recovery email address
  Step 7  — (if set_email) Enter the OTP code Telegram sent to that email
  Step 8  — (if change_2fa & no new_2fa in DB) Enter new 2FA password
  → Automation runs → account saved → summary report sent to admin
"""

from pyrogram import Client, enums
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pyrogram.errors import (
    FloodWait, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PasswordHashInvalid,
)
# These error classes may not exist in all pyrofork versions — import safely
try:
    from pyrogram.errors import EmailUnverified
except ImportError:
    EmailUnverified = Exception   # fallback: treat as generic Exception
try:
    from pyrogram.errors import NewPasswordRequired
except ImportError:
    NewPasswordRequired = Exception
from info import ADMIN_ID, API_ID, API_HASH
from database import get_config, accounts_col
import asyncio
from datetime import datetime

session_states: dict = {}


# ─────────────────────────────────────────────────────────────
#  /login entry point
# ─────────────────────────────────────────────────────────────

async def login_command(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    # Clean up any stale state / disconnected clients
    await _cleanup_state(message.from_user.id)

    await message.reply_text(
        "📱 **Step 1 / 5 — Phone Number**\n\n"
        "Enter the phone number with country code:\n"
        "_(e.g. +919876543210)_"
    )
    session_states[message.from_user.id] = {"step": "waiting_phone"}


# ─────────────────────────────────────────────────────────────
#  Message handler — called from main.py msg_h
# ─────────────────────────────────────────────────────────────

async def handle_session_message(client: Client, message: Message):
    admin_id = message.from_user.id
    state = session_states.get(admin_id)
    if not state:
        return

    step = state.get("step")

    # ── STEP 1: Phone ────────────────────────────────────────
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
                "temp_client": temp_client,
                "account_password": "",
            }
            await message.reply_text(
                f"✅ OTP sent to `{phone}`.\n\n"
                "📱 **Step 2 / 5 — Telegram OTP**\n\n"
                "Enter the OTP you received (digits only):"
            )
        except FloodWait as e:
            await temp_client.disconnect()
            await message.reply_text(
                f"⚠️ FloodWait: please wait **{e.value}s** then retry /login."
            )
            session_states.pop(admin_id, None)
        except Exception as e:
            await temp_client.disconnect()
            await message.reply_text(f"❌ Error sending code: `{e}`\n\nTry /login again.")
            session_states.pop(admin_id, None)

    # ── STEP 2: Telegram OTP ─────────────────────────────────
    elif step == "waiting_code":
        code        = message.text.strip()
        temp_client = state["temp_client"]
        phone       = state["phone"]
        pch         = state["phone_code_hash"]
        try:
            await temp_client.sign_in(phone, pch, code)
            session_states[admin_id].update({"step": "waiting_country"})
            await message.reply_text(
                "✅ Signed in!\n\n"
                "🌍 **Step 3 / 5 — Country**\n\n"
                "Enter the country name for this account pool:\n_(e.g. India)_"
            )
        except SessionPasswordNeeded:
            session_states[admin_id].update({"step": "waiting_password"})
            await message.reply_text(
                "🔐 **2FA Required**\n\n"
                "This account has Two-Step Verification enabled.\n"
                "Enter the current 2FA password:"
            )
        except (PhoneCodeInvalid, PhoneCodeExpired):
            await message.reply_text(
                "❌ Invalid or expired OTP.\n\nPlease start over with /login."
            )
            await _cleanup_state(admin_id)
        except Exception as e:
            await _notify_failure(client, admin_id, state.get("phone", "?"), str(e))
            await _cleanup_state(admin_id)

    # ── STEP 2b: Existing 2FA password ──────────────────────
    elif step == "waiting_password":
        password    = message.text.strip()
        temp_client = state["temp_client"]
        try:
            await temp_client.check_password(password)
            session_states[admin_id].update({
                "step": "waiting_country",
                "account_password": password,
            })
            await message.reply_text(
                "✅ 2FA verified!\n\n"
                "🌍 **Step 3 / 5 — Country**\n\n"
                "Enter the country name for this account pool:\n_(e.g. India)_"
            )
        except PasswordHashInvalid:
            await message.reply_text("❌ Wrong password. Please try again:")
        except Exception as e:
            await _notify_failure(client, admin_id, state.get("phone", "?"), str(e))
            await _cleanup_state(admin_id)

    # ── STEP 3: Country ──────────────────────────────────────
    elif step == "waiting_country":
        country = message.text.strip().upper()
        session_states[admin_id].update({"step": "waiting_price", "country": country})
        await message.reply_text(
            f"✅ Country: `{country}`\n\n"
            "💰 **Step 4 / 5 — Price**\n\n"
            "Enter the selling price for this account:\n_(e.g. 150)_"
        )

    # ── STEP 4: Price ────────────────────────────────────────
    elif step == "waiting_price":
        try:
            price = float(message.text.strip())
            if price <= 0:
                raise ValueError
            session_states[admin_id]["price"] = price
            await _ask_automation_choices(
                client, admin_id,
                state["temp_client"],
                state["phone"]
            )
        except ValueError:
            await message.reply_text("❌ Invalid price. Please enter a positive number (e.g. `150`):")

    # ── STEP 5a: Recovery email address ─────────────────────
    elif step == "waiting_recovery_email":
        email = message.text.strip()
        if "@" not in email or "." not in email:
            await message.reply_text("❌ That doesn't look like a valid email address. Try again:")
            return
        session_states[admin_id]["recovery_email_input"] = email
        await message.reply_text(
            f"✅ Recovery email: `{email}`\n\n"
            f"📨 Telegram will send a verification code to this email.\n\n"
            f"⚠️ **Please check that inbox now and enter the code below:**"
        )
        # Kick off the automation — it will send the verification email
        # and then wait for the email OTP in the next step
        session_states[admin_id]["step"] = "waiting_email_otp"
        await _process_automation(
            client, admin_id,
            state["temp_client"], state["phone"],
            state["choices"]
        )

    # ── STEP 5b: Email OTP verification ─────────────────────
    elif step == "waiting_email_otp":
        email_code  = message.text.strip()
        temp_client = state["temp_client"]
        phone       = state["phone"]

        await message.reply_text("⏳ Verifying email code with Telegram...")
        try:
            # Confirm / verify the recovery email OTP
            # pyrofork exposes this as confirm_password_email
            await temp_client.confirm_password_email(email_code)
            session_states[admin_id]["email_verified"] = True
            session_states[admin_id]["step"] = "email_verified_continue"
            await message.reply_text("✅ Email verified! Finalising account setup...")
            # Continue automation now that email is confirmed
            await _process_automation(
                client, admin_id,
                temp_client, phone,
                state["choices"]
            )
        except Exception as e:
            err = str(e).lower()
            if "code" in err or "invalid" in err or "expire" in err:
                await message.reply_text(
                    f"❌ Invalid or expired email code.\n\n"
                    f"Please enter the code again (check your email for the latest one):"
                )
                # Stay in waiting_email_otp step
            else:
                await message.reply_text(f"❌ Email verification error: `{e}`\nTrying to continue without email...")
                session_states[admin_id]["email_verified"] = False
                session_states[admin_id]["step"] = "email_verified_continue"
                await _process_automation(
                    client, admin_id,
                    temp_client, phone,
                    state["choices"]
                )

    # ── STEP 5c: New 2FA password (not set in DB) ────────────
    elif step == "waiting_new_2fa":
        from database import update_config
        new_pwd = message.text.strip()
        if len(new_pwd) < 6:
            await message.reply_text("❌ Password too short (min 6 characters). Try again:")
            return
        update_config("admin_2fa", new_pwd)
        session_states[admin_id]["new_2fa_override"] = new_pwd
        await message.reply_text(f"✅ New 2FA password saved: `{new_pwd}`. Running automation...")
        session_states[admin_id]["step"] = "running"
        await _process_automation(
            client, admin_id,
            state["temp_client"], state["phone"],
            state["choices"]
        )


# ─────────────────────────────────────────────────────────────
#  Automation Keyboard — Step 5
# ─────────────────────────────────────────────────────────────

async def _ask_automation_choices(bot: Client, admin_id: int, user_client: Client, phone: str):
    session_states[admin_id]["step"] = "waiting_menu_choice"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚙️ Full Setup  (clean chats + block contacts + 2FA + recovery email)",
            callback_data="setup_all"
        )],
        [InlineKeyboardButton(
            "🧹 Clean Only  (leave groups + block private contacts)",
            callback_data="setup_clean"
        )],
        [InlineKeyboardButton(
            "🛡️ Security Only  (change 2FA password + set recovery email)",
            callback_data="setup_sec"
        )],
        [InlineKeyboardButton(
            "⏩ Skip — Add directly to shop",
            callback_data="setup_skip"
        )],
    ])
    await bot.send_message(
        admin_id,
        f"✅ **Step 5 / 5 — Automation**\n\n"
        f"Account `{phone}` is ready.\n"
        f"Choose the setup type:",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────────────────────
#  Automation Callback Handler
# ─────────────────────────────────────────────────────────────

async def handle_automation_callback(bot: Client, callback: CallbackQuery):
    admin_id = callback.from_user.id
    state    = session_states.get(admin_id)

    if not state or state.get("step") != "waiting_menu_choice":
        await callback.answer("❌ Session expired. Start over with /login.", show_alert=True)
        return

    await callback.answer("Processing...")
    data = callback.data

    choices = {
        "clear_groups":   data in ("setup_all", "setup_clean"),
        "block_contacts": data in ("setup_all", "setup_clean"),
        "change_2fa":     data in ("setup_all", "setup_sec"),
        "set_email":      data in ("setup_all", "setup_sec"),
    }

    try:
        await callback.message.delete()
    except Exception:
        pass

    # setup_skip → just export session and save, no automation
    if data == "setup_skip":
        await _save_account_to_db(bot, admin_id, state)
        return

    session_states[admin_id]["choices"] = choices
    await _process_automation(
        bot, admin_id,
        state["temp_client"], state["phone"],
        choices
    )


# ─────────────────────────────────────────────────────────────
#  Core Automation Engine
# ─────────────────────────────────────────────────────────────

async def _process_automation(
    bot: Client, admin_id: int,
    user_client: Client, phone: str, choices: dict
):
    """
    Runs the chosen automation tasks on `user_client`.
    Handles multi-step flows (email OTP verification) by setting state and returning early.
    When everything is done it exports the session, saves to DB, and sends a summary.
    """
    state  = session_states.get(admin_id, {})
    config = get_config()

    # Resolve 2FA passwords
    new_2fa = (
        state.get("new_2fa_override")
        or config.get("admin_2fa")
    )
    # Resolve recovery email
    recovery_email = (
        state.get("recovery_email_input")
        or config.get("recovery_email")
    )

    # ── Gate: 2FA change required but no new password yet ────
    if choices.get("change_2fa") and not new_2fa:
        session_states[admin_id].update({
            "step": "waiting_new_2fa",
            "choices": choices,
        })
        await bot.send_message(
            admin_id,
            "🔐 **New 2FA password not configured.**\n\n"
            "Enter the new 2FA password to set on this account\n"
            "_(minimum 6 characters)_:"
        )
        return

    # ── Gate: email required but not provided yet ────────────
    if choices.get("set_email") and not recovery_email:
        session_states[admin_id].update({
            "step": "waiting_recovery_email",
            "choices": choices,
        })
        await bot.send_message(
            admin_id,
            "📧 **Recovery email not set.**\n\n"
            "Enter the recovery email address to attach to this account:"
        )
        return

    # ── If we are mid-email-OTP flow, don't re-run automation ─
    current_step = state.get("step", "")
    if current_step == "waiting_email_otp":
        return  # waiting for admin to input the email code

    status_msg = await bot.send_message(admin_id, "⚙️ Running automation — please wait...")

    result_lines  = []
    final_password = state.get("account_password", "")
    email_set_ok   = False

    try:
        # ── 1. Leave groups / channels ───────────────────────
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
                            await asyncio.sleep(0.3)
                        except Exception:
                            pass
                result_lines.append(f"✅ Left {left} group(s)/channel(s)")
            except Exception as e:
                result_lines.append(f"⚠️ Group cleanup error: {e}")

        # ── 2. Block private contacts & clear history ────────
        if choices.get("block_contacts"):
            blocked = 0
            try:
                async for dialog in user_client.get_dialogs():
                    chat = dialog.chat
                    if chat and chat.type in (
                        enums.ChatType.PRIVATE,
                        enums.ChatType.BOT,
                    ):
                        if chat.id == 777000:  # Never block Telegram service
                            continue
                        try:
                            await user_client.delete_chat_history(chat.id, revoke=True)
                            await user_client.block_user(chat.id)
                            blocked += 1
                            await asyncio.sleep(0.3)
                        except Exception:
                            pass
                result_lines.append(f"✅ Blocked {blocked} contact(s) & cleared history")
            except Exception as e:
                result_lines.append(f"⚠️ Block contacts error: {e}")

        # ── 3. 2FA change / enable ───────────────────────────
        if choices.get("change_2fa") and new_2fa:
            try:
                hint           = "Hind Deals"
                existing_pwd   = state.get("account_password", "")

                if existing_pwd:
                    # Account already has 2FA — change the password
                    await user_client.change_cloud_password(
                        current_password=existing_pwd,
                        new_password=new_2fa,
                        new_hint=hint,
                    )
                    result_lines.append(f"✅ 2FA password changed → `{new_2fa}`")
                else:
                    # No 2FA yet — enable it.
                    # If we also need to set email, pass it here so Telegram sends
                    # the verification OTP to that email in one combined call.
                    if choices.get("set_email") and recovery_email:
                        try:
                            await user_client.enable_cloud_password(
                                password=new_2fa,
                                hint=hint,
                                email=recovery_email,
                            )
                            result_lines.append(f"✅ 2FA enabled → `{new_2fa}`")
                            result_lines.append(
                                f"📧 Telegram sent email verification code to `{recovery_email}`"
                            )
                            # Now we MUST wait for admin to type the email OTP
                            session_states[admin_id].update({
                                "step": "waiting_email_otp",
                                "choices": choices,
                                "final_password_so_far": new_2fa,
                                "result_lines_so_far": result_lines,
                            })
                            final_password = new_2fa
                            # Tell admin
                            await status_msg.edit_text(
                                "📧 **Email Verification Required**\n\n"
                                f"Telegram sent a verification code to:\n`{recovery_email}`\n\n"
                                "Please check that inbox and enter the code here:"
                            )
                            return  # ← come back when admin types the email OTP
                        except Exception as e:
                            result_lines.append(f"⚠️ 2FA+email enable error: {e}")
                    else:
                        # Enable 2FA without email
                        await user_client.enable_cloud_password(
                            password=new_2fa,
                            hint=hint,
                        )
                        result_lines.append(f"✅ 2FA enabled → `{new_2fa}`")

                final_password = new_2fa

            except Exception as e:
                result_lines.append(f"⚠️ 2FA error: {e}")

        # ── 4. Set recovery email (if not done via enable_cloud_password) ──
        if choices.get("set_email") and recovery_email and not state.get("email_verified"):
            # We land here only if:
            #   a) Account already had 2FA (change_cloud_password was used above, no email param)
            #   b) OR change_2fa was False but set_email was True
            try:
                current_pwd = final_password or state.get("account_password", "")
                if current_pwd:
                    # Strategy: remove 2FA then re-enable with email so Telegram sends verification
                    await user_client.remove_cloud_password(current_pwd)
                    await user_client.enable_cloud_password(
                        password=current_pwd,
                        hint="Hind Deals",
                        email=recovery_email,
                    )
                    result_lines.append(
                        f"📧 Telegram sent email verification code to `{recovery_email}`"
                    )
                    session_states[admin_id].update({
                        "step": "waiting_email_otp",
                        "choices": choices,
                        "final_password_so_far": current_pwd,
                        "result_lines_so_far": result_lines,
                    })
                    await status_msg.edit_text(
                        "📧 **Email Verification Required**\n\n"
                        f"Telegram sent a verification code to:\n`{recovery_email}`\n\n"
                        "Please check that inbox and enter the code here:"
                    )
                    return  # wait for email OTP
                else:
                    result_lines.append(
                        "⚠️ Skipped recovery email — no active 2FA password available"
                    )
            except Exception as e:
                result_lines.append(f"⚠️ Recovery email error: {e}")

        # ── 4b. Email already verified in a previous sub-step ─
        if state.get("email_verified"):
            email_set_ok = True
            result_lines = list(state.get("result_lines_so_far", result_lines))
            result_lines.append(f"✅ Recovery email verified & set → `{recovery_email}`")
            final_password = state.get("final_password_so_far", final_password) or final_password

    except Exception as e:
        result_lines.append(f"❌ Unexpected automation error: {e}")

    # ── Save account to DB & send final summary ───────────────
    await _finalise_and_save(
        bot, admin_id, state, user_client, phone,
        result_lines, final_password,
        recovery_email if email_set_ok else None,
        status_msg
    )


# ─────────────────────────────────────────────────────────────
#  Finalise — export session, upsert DB, send summary
# ─────────────────────────────────────────────────────────────

async def _finalise_and_save(
    bot: Client, admin_id: int, state: dict,
    user_client: Client, phone: str,
    result_lines: list, final_password: str,
    verified_email,    # str or None
    status_msg
):
    country = state.get("country", "GLOBAL")
    price   = state.get("price", 0.0)

    try:
        session_string = await user_client.export_session_string()
        await user_client.disconnect()
        result_lines.append("✅ Session exported successfully")
    except Exception as e:
        result_lines.append(f"❌ Session export failed: {e}")
        session_string = None

    if session_string:
        # Use upsert so no duplicate documents if phone already exists
        accounts_col.update_one(
            {"phone": phone},
            {"$set": {
                "session_string": session_string,
                "country":        country,
                "price":          price,
                "status":         "available",
                "password":       final_password or "",
                "recovery_email": verified_email or "",
                "added_at":       datetime.utcnow(),
            }},
            upsert=True
        )
        result_lines.append(f"✅ Saved to DB — Pool: {country}, Price: ₹{price}")
    else:
        result_lines.append("❌ Account NOT saved — session export failed")

    # ── Build summary report ──────────────────────────────────
    summary_lines = "\n".join(result_lines)
    report = (
        f"🎉 **AUTOMATION COMPLETE**\n\n"
        f"📱 **Phone:** `{phone}`\n"
        f"🌍 **Country:** `{country}`\n"
        f"💰 **Price:** ₹{price}\n"
        f"🔐 **2FA Password:** `{final_password or '— not changed —'}`\n"
        f"📧 **Recovery Email:** `{verified_email or '— not set —'}`\n\n"
        f"─────────────────\n"
        f"📋 **Steps Completed:**\n{summary_lines}"
    )

    try:
        await status_msg.edit_text(report)
    except Exception:
        await bot.send_message(admin_id, report)

    session_states.pop(admin_id, None)


# ─────────────────────────────────────────────────────────────
#  Skip — just save without automation
# ─────────────────────────────────────────────────────────────

async def _save_account_to_db(bot: Client, admin_id: int, state: dict):
    """Export session and save directly, no automation steps."""
    phone          = state["phone"]
    temp_client    = state["temp_client"]
    country        = state.get("country", "GLOBAL")
    price          = state.get("price", 0.0)
    account_password = state.get("account_password", "")

    try:
        session_string = await temp_client.export_session_string()
        await temp_client.disconnect()

        accounts_col.update_one(
            {"phone": phone},
            {"$set": {
                "session_string": session_string,
                "country":        country,
                "price":          price,
                "status":         "available",
                "password":       account_password or "",
                "recovery_email": "",
                "added_at":       datetime.utcnow(),
            }},
            upsert=True
        )
        await bot.send_message(
            admin_id,
            f"✅ **Account added (no automation)**\n\n"
            f"📱 Phone: `{phone}`\n"
            f"🌍 Country: `{country}`\n"
            f"💰 Price: ₹{price}\n"
            f"🔐 2FA: `{account_password or '— not set —'}`\n"
            f"📧 Recovery Email: `— not set —`"
        )
    except Exception as e:
        await bot.send_message(admin_id, f"❌ Failed to save account: `{e}`")

    session_states.pop(admin_id, None)


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

async def _cleanup_state(admin_id: int):
    """Disconnect any open temp client and remove state."""
    state = session_states.pop(admin_id, None)
    if state:
        tc = state.get("temp_client")
        if tc:
            try:
                await tc.disconnect()
            except Exception:
                pass


async def _notify_failure(bot: Client, admin_id: int, phone: str, error: str):
    await bot.send_message(
        admin_id,
        f"❌ **Login failed for** `{phone}`\n\n"
        f"Error: `{error}`\n\n"
        f"Restart with /login."
    )
