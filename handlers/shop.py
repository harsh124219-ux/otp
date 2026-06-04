from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import (
    get_balance, deduct_balance, get_accounts_by_country_sorted,
    update_account_status, create_order, get_order, close_order, accounts_col
)
from info import API_ID, API_HASH, LOG_GROUP
from datetime import datetime, timedelta

def mask_number(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return phone[:4] + "***" + phone[-3:]

async def shop_menu(client: Client, message: Message):
    if isinstance(message, CallbackQuery):
        message = message.message

    countries = accounts_col.distinct("country", {"status": "available"})

    if not countries:
        # Match identical UI formatting for both Callback & direct Commands
        text = "🛒 **SHOP**\n\n❌ No accounts available at the moment."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        if hasattr(message, "edit_text") and message.from_user.id == client.me.id:
            await message.edit_text(text, reply_markup=markup)
        else:
            await message.reply_text(text, reply_markup=markup)
        return

    buttons = []
    for country in sorted(countries):
        count = accounts_col.count_documents({"status": "available", "country": country})
        buttons.append([
            InlineKeyboardButton(f"🌍 {country} ({count} available)", callback_data=f"sort_opts_{country}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
    
    text = "🛒 **SHOP**\n\nSelect a country to view stock:"
    markup = InlineKeyboardMarkup(buttons)
    
    # Check if we can edit or must reply (for text commands like /shop)
    if hasattr(message, "edit_text") and message.from_user.id == client.me.id:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)

async def sort_options_menu(client: Client, callback: CallbackQuery):
    country = callback.data.replace("sort_opts_", "")
    buttons = [
        [InlineKeyboardButton("📉 Cheapest to Expensive", callback_data=f"view_country_{country}_low")],
        [InlineKeyboardButton("📈 Expensive to Cheapest", callback_data=f"view_country_{country}_high")],
        [InlineKeyboardButton("🔙 Back to Shop", callback_data="open_shop")]
    ]
    await callback.message.edit_text(
        f"📊 **Sorting Preference for {country}**\n\nHow would you like to view the price list?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def view_country_accounts(client: Client, callback: CallbackQuery):
    parts = callback.data.split("_")
    country = parts[2]
    sort_type = parts[3] if len(parts) > 3 else "low"
    sort_order = "low_to_high" if sort_type == "low" else "high_to_low"

    accounts = get_accounts_by_country_sorted(country, sort_order)
    if not accounts:
        await callback.answer("❌ Out of stock in this category.", show_alert=True)
        return

    selected = accounts[0]
    price = selected["price"]
    phone = selected["phone"]

    text = f"🌍 **Country:** {country.upper()}\n💰 **Account Price:** ₹{price}\n\nClick below to buy this item."
    buttons = [
        [InlineKeyboardButton(f"💳 Buy Now - ₹{price}", callback_data=f"buy_acc_{phone}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"sort_opts_{country}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_account(client: Client, callback: CallbackQuery):
    phone = callback.data.replace("buy_acc_", "")
    user_id = callback.from_user.id

    account = accounts_col.find_one({"phone": phone, "status": "available"})
    if not account:
        await callback.answer("❌ Account sold out.", show_alert=True)
        return

    price = account["price"]
    if get_balance(user_id) < price:
        await callback.answer(f"❌ Insufficient balance! Needs ₹{price}", show_alert=True)
        return

    if not deduct_balance(user_id, price):
        await callback.answer("❌ Error processing payment.", show_alert=True)
        return

    update_account_status(phone, "sold")
    order_id = create_order(user_id, phone, account["session_string"], account["country"], price)

    await callback.message.edit_text(
        f"🎉 **Purchase Successful!**\n\n📱 Number: `{phone}`\n💰 Cost: ₹{price}\n\n"
        f"Go to **My Orders** section to request your code updates.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Open Orders Menu", callback_data="open_orders")]])
    )

async def get_otp_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("get_otp_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("Order details invalid.", show_alert=True)
        return

    await callback.answer("⏳ Checking Telegram for fresh code alerts...", show_alert=False)

    try:
        user_client = Client(f"s_{order['phone']}", API_ID, API_HASH, session_string=order["session_string"], in_memory=True)
        await user_client.connect()

        otp_msg = "❌ No codes found yet. Please send a new code request from your device."
        fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)

        async for m in user_client.get_chat_history(777000, limit=5):
            if m.date and m.date >= fifteen_minutes_ago:
                if m.text:
                    otp_msg = m.text
                    break

        await user_client.disconnect()
        
        await callback.message.reply_text(
            f"📩 **OTP FOR** `{order['phone']}` (Last 15m):\n\n`{otp_msg}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh New OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🚪 Logout & Close Session", callback_data=f"logout_acc_{order_id}")]
            ])
        )
    except Exception as e:
        await callback.message.reply_text(f"❌ Error communicating with Telegram session: `{e}`")

async def logout_acc_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("logout_acc_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("Active session record missing.", show_alert=True)
        return

    try:
        user_client = Client(f"s_{order['phone']}", API_ID, API_HASH, session_string=order["session_string"], in_memory=True)
        await user_client.connect()
        await user_client.log_out()
        close_order(order_id)

        log_text = (
            f"🛒 🛍️ **NEW COMPLETED SALE DONE**\n\n"
            f"👤 **Buyer ID:** `{order['user_id']}`\n"
            f"📱 **Phone Number:** `{order['phone']}`\n"
            f"🌍 **Country Pool:** {order['country']}\n"
            f"💰 **Final Price Paid:** ₹{order['price']}\n"
            f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await client.send_message(chat_id=LOG_GROUP, text=log_text)

        await callback.message.edit_text(
            f"✅ Successfully logged out from account `{order['phone']}`. Session is now finalized.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )
    except Exception as e:
        await callback.message.reply_text(f"❌ Session closure issue: `{e}`")
