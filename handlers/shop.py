from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from info import COUNTRY_PRICES, API_ID, API_HASH
from database import (
    get_balance, deduct_balance, get_available_account, 
    update_account_status, create_order, get_order, close_order
)
import asyncio
from datetime import datetime

async def shop_menu(client: Client, message: Message):
    buttons = []
    for country, price in COUNTRY_PRICES.items():
        buttons.append([InlineKeyboardButton(f"{country} - ₹{price}", callback_data=f"buy_country_{country}")])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
    
    await message.edit_text(
        "🛒 **SELECT COUNTRY**\n\nChoose a country to purchase a Telegram account:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def buy_country(client: Client, callback: CallbackQuery):
    country = callback.data.replace("buy_country_", "")
    price = COUNTRY_PRICES.get(country)
    user_id = callback.from_user.id
    
    balance = get_balance(user_id)
    if balance < price:
        await callback.answer(f"❌ Insufficient balance! Required: ₹{price}", show_alert=True)
        return

    # Check for available account
    account = get_available_account(country)
    if not account:
        await callback.answer(f"⚠️ No accounts available for {country} right now.", show_alert=True)
        return

    # Process Purchase
    if deduct_balance(user_id, price):
        # Assign account to user
        update_account_status(account["phone"], "sold")
        order_id = create_order(user_id, account["phone"], account["session_string"], country, price)
        
        await callback.message.edit_text(
            f"✅ **Purchase Successful!**\n\n"
            f"🌍 Country: {country}\n"
            f"📱 Phone: `{account['phone']}`\n"
            f"💰 Price: ₹{price}\n"
            f"🆔 Order ID: `{order_id}`\n\n"
            "You can now get OTPs for this account from the 'Orders' section.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Get OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🔙 Back to Shop", callback_data="open_shop")]
            ])
        )
    else:
        await callback.answer("❌ Error processing transaction.", show_alert=True)

async def get_otp_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("get_otp_", "")
    order = get_order(order_id)
    
    if not order or order["status"] == "closed":
        await callback.answer("❌ This order is no longer active.", show_alert=True)
        return

    await callback.answer("⏳ Fetching latest OTP...")
    
    try:
        user_client = Client(
            f"session_{order['phone']}", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            session_string=order["session_string"], 
            in_memory=True
        )
        await user_client.connect()
        
        otp_text = "No recent OTP found."
        # Check Telegram (777000)
        async for msg in user_client.get_chat_history(777000, limit=1):
            otp_text = msg.text if msg.text else "Non-text message."
        
        await user_client.disconnect()
        
        await callback.message.reply_text(
            f"📩 **LATEST OTP FOR {order['phone']}**\n\n"
            f"`{otp_text}`\n\n"
            f"🕒 Time: {datetime.now().strftime('%H:%M:%S')}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🚪 Logout Account", callback_data=f"logout_acc_{order_id}")]
            ])
        )
    except Exception as e:
        await callback.message.reply_text(f"❌ Error fetching OTP: {str(e)}")

async def logout_acc_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("logout_acc_", "")
    order = get_order(order_id)
    
    if not order:
        return

    try:
        user_client = Client(
            f"session_{order['phone']}", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            session_string=order["session_string"], 
            in_memory=True
        )
        await user_client.connect()
        await user_client.log_out()
        close_order(order_id)
        
        await callback.message.edit_text(
            f"✅ **Logged out from {order['phone']}**\n\n"
            "The account has been removed from your active orders."
        )
    except Exception as e:
        await callback.answer(f"❌ Error during logout: {str(e)}", show_alert=True)
