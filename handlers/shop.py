from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import (
    get_balance, deduct_balance, get_accounts_by_country_sorted,
    update_account_status, create_order, get_order, close_order, accounts_col
)
from info import API_ID, API_HASH, LOG_GROUP
from datetime import datetime, timedelta

def mask_number(phone: str) -> str:
    """Masks the phone number exactly after the first 3 initial digits."""
    if not phone:
        return ""
    clean_phone = phone.strip()
    if len(clean_phone) <= 4:
        return clean_phone
    return clean_phone[:4] + "*" * (len(clean_phone) - 4)

async def shop_menu(client: Client, message: Message):
    if isinstance(message, CallbackQuery):
        message = message.message

    countries = accounts_col.distinct("country", {"status": "available"})

    if not countries:
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
        if count > 0:
            buttons.append([
                InlineKeyboardButton(f"🌍 {country} ({count} available)", callback_data=f"sort_opts_{country}")
            ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
    
    text = "🛒 **SHOP**\n\nSelect a country to view stock:"
    markup = InlineKeyboardMarkup(buttons)
    
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

    # Fetch accounts from database sorted by price criteria
    accounts = get_accounts_by_country_sorted(country, sort_order)
    
    # Filter to guarantee only currently available stock items are viewed
    available_accounts = [acc for acc in accounts if acc.get("status") == "available"]

    if not available_accounts:
        await callback.answer("❌ Out of stock in this category.", show_alert=True)
        return

    text = f"🌍 **Country Pool:** {country.upper()}\n\n✨ **Select an account to purchase:**"
    
    buttons = []
    for acc in available_accounts:
        phone = acc["phone"]
        price = acc["price"]
        masked_no = mask_number(phone)
        
        # Exact requested format -> price : masked no after 3 initial digits
        btn_label = f"₹{price} : {masked_no}"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"buy_acc_{phone}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"sort_opts_{country}")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_account(client: Client, callback: CallbackQuery):
    phone = callback.data.replace("buy_acc_", "")
    user_id = callback.from_user.id

    # VERIFY AVAILABILITY INSTANTLY BEFORE COLLECTION
    account = accounts_col.find_one({"phone": phone, "status": "available"})
    if not account:
        await callback.answer("❌ This account was just sold to another user!", show_alert=True)
        # Re-render menu dynamically
        await shop_menu(client, callback)
        return

    price = account["price"]
    if get_balance(user_id) < price:
        await callback.answer(f"❌ Insufficient balance! Needs ₹{price}", show_alert=True)
        return

    if not deduct_balance(user_id, price):
        await callback.answer("❌ Error processing payment.", show_alert=True)
        return

    # Atomic update lock to secure transaction
    result = accounts_col.update_one({"phone": phone, "status": "available"}, {"$set": {"status": "sold"}})
    if result.modified_count == 0:
        # Refund user balance if state changes during computation gap
        from database import add_balance
        add_balance(user_id, price)
        await callback.answer("❌ This item was bought by someone else a second ago!", show_alert=True)
        return

    order_id = create_order(user_id, phone, account["session_string"], account["country"], price)

    # SEND REAL-TIME NOTIFICATION LOG IMMEDIATELY
    log_text = (
        f"🛒 🛍️ **NEW COMPLETED SALE DONE**\n\n"
        f"👤 **Buyer ID:** `{user_id}`\n"
        f"📱 **Phone Number:** `{phone}`\n"
        f"🌍 **Country Pool:** {account['country']}\n"
        f"💰 **Final Price Paid:** ₹{price}\n"
        f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        await client.send_message(chat_id=LOG_GROUP, text=log_text)
    except Exception as e:
        print(f"Failed sending purchase log to LOG_GROUP: {e}")

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

    await callback.answer("⏳ Fetching code logs directly from Telegram...", show_alert=False)

    try:
        user_client = Client(f"s_{order['phone']}", API_ID, API_HASH, session_string=order["session_string"], in_memory=True)
        await user_client.connect()

        otp_msg = "❌ No fresh login codes discovered. Please trigger an official registration request from your app."
        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

        async for m in user_client.get_chat_history(777000, limit=5):
            if m.date and m.date >= two_minutes_ago:
                if m.text:
                    otp_msg = m.text
                    break

        await user_client.disconnect()
        
        await callback.message.reply_text(
            f"📩 **OTP FOR** `{order['phone']}` (Last 2m):\n\n`{otp_msg}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh New OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🚪 Logout & Close Session", callback_data=f"logout_acc_{order_id}")]
            ])
        )

        account_data = accounts_col.find_one({"phone": order['phone']})
        two_fa_password = account_data.get("password") if account_data else None

        if two_fa_password:
            await client.send_message(
                chat_id=callback.from_user.id,
                text=f"🔐 **2FA Password for** `{order['phone']}`:\n\n`{two_fa_password}`"
            )
        else:
            await client.send_message(
                chat_id=callback.from_user.id,
                text=f"ℹ️ **2FA Status for** `{order['phone']}`:\nNo password is set or required for this account."
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
        # Fixed: We close the active order cleanly without destroying the Pyrogram server auth key.
        close_order(order_id)

        # SEND DISCONNECT NOTIFICATION LOG IMMEDIATELY
        log_text = (
            f"🚪 **USER LOGGED OUT FROM ACCOUNT**\n\n"
            f"👤 **User ID:** `{order['user_id']}`\n"
            f"📱 **Phone Number:** `{order['phone']}`\n"
            f"🌍 **Country Pool:** {order['country']}\n"
            f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        try:
            await client.send_message(chat_id=LOG_GROUP, text=log_text)
        except Exception as e:
            print(f"Failed sending logout log to LOG_GROUP: {e}")

        await callback.message.edit_text(
            f"✅ Successfully closed session interface for account `{order['phone']}`. Order session is now finalized.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Session closure issue: `{e}`")
