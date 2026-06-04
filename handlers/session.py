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
            # Code verified, transition to asking for country name next
            session_states[admin_id]["step"] = "waiting_country"
            await message.reply_text("🌍 Now enter the **Country Name** for this account (e.g., India):")
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
            # Password verified, transition to asking for country name next
            session_states[admin_id]["step"] = "waiting_country"
            await message.reply_text("🌍 Now enter the **Country Name** for this account (e.g., India):")
        except PasswordHashInvalid:
            await message.reply_text("❌ Incorrect password. Please try again:")
        except Exception as e:
            await notify_admin_failure(client, admin_id, phone, f"Password check error: {str(e)}")
            session_states.pop(admin_id, None)

    elif step == "waiting_country":
        country_name = message.text.strip().upper()
        session_states[admin_id]["country"] = country_name
        session_states[admin_id]["step"] = "waiting_price"
        await message.reply_text(f"🌍 Country set to `{country_name}`.\n\n💰 Now enter the **Price** of the account in ₹ (e.g., 150):")

    elif step == "waiting_price":
        try:
            price_val = float(message.text.strip())
            session_states[admin_id]["price"] = price_val
            
            temp_client = state["temp_client"]
            phone = state["phone"]
            # Proceed to automation setup with our provided data parameters
            await process_account_automation(client, admin_id, temp_client, phone)
        except ValueError:
            await message.reply_text("❌ Invalid entry. Please enter a numerical value for price:")

    elif step == "waiting_recovery_email":
        email = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        from database import update_config
        update_config("recovery_email", email)
        await message.reply_text(f"✅ Recovery email set to `{email}`. Proceeding...")
        await process_account_automation(client, admin_id, temp_client, phone)

    elif step == "waiting_admin_2fa":
        password = message.text.strip()
        temp_client = state["temp_client"]
        phone = state["phone"]
        from database import update_config
        update_config("admin_2fa", password)
        await message.reply_text(f"✅ Admin 2FA set to `{password}`. Proceeding...")
        await process_account_automation(client, admin_id, temp_client, phone)


async def process_account_automation(bot: Client, admin_id: int, user_client: Client, phone: str):
    state = session_states.get(admin_id)
    country = state.get("country", "AUTO")
    price = state.get("price", 0.0)

    config = get_config()
    recovery_email = config.get("recovery_email")
    admin_2fa = config.get("admin_2fa")

    if not recovery_email:
        session_states[admin_id]["step"] = "waiting_recovery_email"
        await bot.send_message(admin_id, "📧 Recovery mail is not set. Please send the recovery email to use:")
        return

    if not admin_2fa:
        session_states[admin_id]["step"] = "waiting_admin_2fa"
        await bot.send_message(admin_id, "🔐 Admin 2FA password is not set. Please send the password to set:")
        return

    await bot.send_message(admin_id, "⚙️ **Starting automation...**\n- Changing recovery email\n- Changing 2FA password\n- Cleaning up chats/channels")

    try:
        try:
            try:
                await user_client.set_password(new_password=admin_2fa, email=recovery_email)
                await bot.send_message(admin_id, "✅ 2FA password set successfully.")
            except Exception as e:
                await bot.send_message(admin_id, f"⚠️ Could not set/update 2FA password for {phone}: `{e}`")
        except Exception as outer_e:
            await bot.send_message(admin_id, f"❌ Session processing error: `{outer_e}`")

        await bot.send_message(admin_id, "✅ Recovery email and 2FA handling completed.")

        async for dialog in user_client.get_dialogs():
            if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
                try:
                    await user_client.leave_chat(dialog.chat.id)
                except:
                    pass
            elif dialog.chat.type in [enums.ChatType.PRIVATE, enums.ChatType.BOT]:
                if dialog.chat.id != 777000:
                    try:
                        await user_client.block_user(dialog.chat.id)
                    except:
                        pass
        
        await bot.send_message(admin_id, "✅ Chats cleaned and older contacts blocked.")

        session_string = await user_client.export_session_string()
        await user_client.disconnect()
        
        # Save to database using custom pricing and country values
        add_account(phone, session_string, country, price)
        
        await bot.send_message(admin_id, f"🎉 **Account {phone} added successfully!**\n🌍 Country Pool: {country}\n💰 Cost: ₹{price}")
        session_states.pop(admin_id, None)

    except Exception as e:
        await notify_admin_failure(bot, admin_id, phone, str(e))
        session_states.pop(admin_id, None)


async def notify_admin_failure(bot: Client, admin_id: int, phone: str, error: str):
    await bot.send_message(
        admin_id, 
        f"❌ **Automation Failed for {phone}**\n\nError: `{error}`\n\nPlease check the account manually."
    )
