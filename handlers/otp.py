from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from info import OTP_PRICE, API_ID, API_HASH
from database import get_balance, deduct_balance, get_session, log_otp_sale
import asyncio

async def buy_otp_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    balance = get_balance(user_id)

    if balance < OTP_PRICE:
        await callback.answer(f"❌ Insufficient balance! Price: ₹{OTP_PRICE}", show_alert=True)
        return

    # Check if session exists
    session_string = get_session()
    if not session_string:
        await callback.answer("⚠️ Service currently unavailable (No session). Contact Admin.", show_alert=True)
        return

    await callback.message.edit_text("⏳ Processing your OTP request...")

    # Deduct balance
    if not deduct_balance(user_id, OTP_PRICE):
        await callback.message.edit_text("❌ Failed to deduct balance. Try again.")
        return

    # Start delivery process
    success = await deliver_otp(client, user_id, session_string)
    
    if not success:
        # Refund if failed
        from database import add_balance
        add_balance(user_id, OTP_PRICE)
        await client.send_message(user_id, "❌ Delivery failed. Your balance has been refunded.")

async def deliver_otp(client: Client, user_id: int, session_string: str):
    try:
        # Use the stored session to login
        user_client = Client("delivery_session", api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
        await user_client.connect()

        # Logic to fetch content/OTP
        # For demonstration, we'll fetch the latest message from a specific service or just send a dummy OTP
        # In a real scenario, you might search for messages from "Telegram" or "Google" etc.
        
        # Example: Get the last message from Telegram (ID 777000)
        otp_content = "No OTP found."
        async for message in user_client.get_chat_history(777000, limit=1):
            otp_content = message.text if message.text else "Non-text message received."

        await user_client.disconnect()

        # Log the sale
        log_otp_sale(user_id, otp_content, OTP_PRICE)

        # Deliver to user
        await client.send_message(
            user_id,
            f"✅ **OTP Delivered!**\n\n"
            f"📝 Content:\n`{otp_content}`\n\n"
            f"💰 Price: ₹{OTP_PRICE}\n"
            f"📅 Time: {__import__('datetime').datetime.now().strftime('%H:%M:%S')}"
        )
        return True

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await deliver_otp(client, user_id, session_string)
    except Exception as e:
        print(f"Delivery Error: {e}")
        return False
