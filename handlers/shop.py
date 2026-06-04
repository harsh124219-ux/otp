from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import (
    get_balance, deduct_balance, get_accounts_by_country_sorted,
    update_account_status, create_order, get_order, close_order, accounts_col
)
from info import API_ID, API_HASH, LOG_GROUP
# FIX BUG 5: import timezone for aware datetime comparison
from datetime import datetime, timedelta, timezone


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def mask_number(phone: str) -> str:
    """Masks the phone number after the first 4 characters (e.g. +91*******0)."""
    if not phone:
        return ""
    clean = phone.strip()
    if len(clean) <= 4:
        return clean
    return clean[:4] + "*" * (len(clean) - 4)


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.reply_text(text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────
#  Shop Menu
# ─────────────────────────────────────────────────────────────

async def shop_menu(client: Client, update):
    is_cb = isinstance(update, CallbackQuery)
    message = update.message if is_cb else update

    countries = accounts_col.distinct("country", {"status": "available"})

    if not countries:
        text = "🛒 **SHOP**\n\n❌ No accounts available at the moment.\nCheck back soon!"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        if is_cb:
            await _edit(update, text, markup)
        else:
            await message.reply_text(text, reply_markup=markup)
        return

    buttons = []
    for country in sorted(countries):
        count = accounts_col.count_documents({"status": "available", "country": country})
        if count > 0:
            buttons.append([
                InlineKeyboardButton(
                    f"🌍 {country}  ({count} available)",
                    callback_data=f"sort_opts_{country}"
                )
            ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
    text = "🛒 **SHOP**\n\nSelect a country to view available accounts:"
    markup = InlineKeyboardMarkup(buttons)

    if is_cb:
        await _edit(update, text, markup)
    else:
        await message.reply_text(text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────
#  Sort Options
# ─────────────────────────────────────────────────────────────

async def sort_options_menu(client: Client, callback: CallbackQuery):
    country = callback.data.replace("sort_opts_", "")
    buttons = [
        [InlineKeyboardButton("📉 Cheapest First", callback_data=f"view_country_{country}_low")],
        [InlineKeyboardButton("📈 Most Expensive First", callback_data=f"view_country_{country}_high")],
        [InlineKeyboardButton("🔙 Back to Shop", callback_data="open_shop")]
    ]
    await _edit(
        callback,
        f"📊 **Sort Preference — {country}**\n\nHow would you like to sort the price list?",
        InlineKeyboardMarkup(buttons)
    )


# ─────────────────────────────────────────────────────────────
#  Country Account List
# ─────────────────────────────────────────────────────────────

async def view_country_accounts(client: Client, callback: CallbackQuery):
    parts = callback.data.split("_")
    sort_type = parts[-1]
    country   = "_".join(parts[2:-1])

    sort_order = "low_to_high" if sort_type == "low" else "high_to_low"
    accounts = get_accounts_by_country_sorted(country, sort_order)
    available_accounts = [a for a in accounts if a.get("status") == "available"]

    if not available_accounts:
        await callback.answer("❌ Out of stock in this category.", show_alert=True)
        await shop_menu(client, callback)
        return

    text = (
        f"🌍 **{country.upper()} — Available Accounts**\n\n"
        f"💡 Tap any account to purchase it.\n"
        f"_Showing {len(available_accounts)} item(s)_"
    )

    buttons = []
    for acc in available_accounts:
        phone  = acc["phone"]
        price  = acc["price"]
        masked = mask_number(phone)
        buttons.append([
            InlineKeyboardButton(f"₹{price}  —  {masked}", callback_data=f"buy_acc_{phone}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"sort_opts_{country}")])
    await _edit(callback, text, InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────
#  Buy Account
# ─────────────────────────────────────────────────────────────

async def buy_account(client: Client, callback: CallbackQuery):
    phone   = callback.data.replace("buy_acc_", "")
    user_id = callback.from_user.id

    account = accounts_col.find_one({"phone": phone, "status": "available"})
    if not account:
        await callback.answer("❌ This account was just sold to someone else!", show_alert=True)
        await shop_menu(client, callback)
        return

    price = account["price"]
    if get_balance(user_id) < price:
        await callback.answer(f"❌ Insufficient balance! You need ₹{price}", show_alert=True)
        return

    if not deduct_balance(user_id, price):
        await callback.answer("❌ Payment error. Please try again.", show_alert=True)
        return

    result = accounts_col.update_one(
        {"phone": phone, "status": "available"},
        {"$set": {"status": "sold"}}
    )
    if result.modified_count == 0:
        from database import add_balance
        add_balance(user_id, price)
        await callback.answer("❌ Someone bought this a split second before you! Refunded.", show_alert=True)
        await shop_menu(client, callback)
        return

    order_id = create_order(
        user_id, phone,
        account["session_string"],
        account["country"],
        price
    )

    log_text = (
        f"🛒 **NEW SALE**\n\n"
        f"👤 Buyer: `{user_id}`\n"
        f"📱 Phone: `{phone}`\n"
        f"🌍 Country: {account['country']}\n"
        f"💰 Price: ₹{price}\n"
        f"🆔 Order: `{order_id}`\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        await client.send_message(chat_id=LOG_GROUP, text=log_text)
    except Exception as e:
        print(f"[LOG] Failed to send purchase log: {e}")

    await _edit(
        callback,
        f"🎉 **Purchase Successful!**\n\n"
        f"📱 Number: `{phone}`\n"
        f"💰 Paid: ₹{price}\n"
        f"🆔 Order ID: `{order_id}`\n\n"
        f"Use **My Orders** to fetch OTP codes.",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 My Orders", callback_data="open_orders")],
            [InlineKeyboardButton("🛒 Buy Another", callback_data="open_shop")]
        ])
    )


# ─────────────────────────────────────────────────────────────
#  OTP Fetch
# ─────────────────────────────────────────────────────────────

async def get_otp_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("get_otp_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("❌ Order not found.", show_alert=True)
        return

    await callback.answer("⏳ Connecting to Telegram session...", show_alert=False)

    try:
        user_client = Client(
            f"s_{order['phone']}",
            API_ID, API_HASH,
            session_string=order["session_string"],
            in_memory=True
        )
        await user_client.connect()

        otp_msg = None
        # FIX BUG 5: use timezone-aware datetime so comparison with m.date works
        two_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=2)

        async for m in user_client.get_chat_history(777000, limit=5):
            if m.date and m.date >= two_minutes_ago and m.text:
                otp_msg = m.text
                break

        await user_client.disconnect()

        if otp_msg:
            result_text = (
                f"📩 **OTP for** `{order['phone']}`\n"
                f"_(last 2 minutes)_\n\n"
                f"`{otp_msg}`"
            )
        else:
            result_text = (
                f"📩 **OTP for** `{order['phone']}`\n\n"
                f"❌ No fresh OTP found in the last 2 minutes.\n\n"
                f"👉 Trigger a login request from your app, then refresh."
            )

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh OTP", callback_data=f"get_otp_{order_id}")],
            [InlineKeyboardButton("🚪 Close Session", callback_data=f"logout_acc_{order_id}")],
            [InlineKeyboardButton("🔙 Back to Orders", callback_data="open_orders")]
        ])

        await callback.message.reply_text(result_text, reply_markup=markup)

        account_data = accounts_col.find_one({"phone": order["phone"]})
        two_fa = account_data.get("password") if account_data else None
        recovery_email = account_data.get("recovery_email") if account_data else None

        if two_fa:
            info_lines = [f"🔐 **2FA Password:** `{two_fa}`"]
            if recovery_email:
                info_lines.append(f"📧 **Recovery Email:** `{recovery_email}`")
            await client.send_message(
                callback.from_user.id,
                "\n".join(info_lines)
            )

    except Exception as e:
        await callback.message.reply_text(f"❌ Session error: `{e}`")


# ─────────────────────────────────────────────────────────────
#  Logout / Close Session
# ─────────────────────────────────────────────────────────────

async def logout_acc_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("logout_acc_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("❌ Order record not found.", show_alert=True)
        return

    try:
        close_order(order_id)

        log_text = (
            f"🚪 **SESSION CLOSED**\n\n"
            f"👤 User: `{order['user_id']}`\n"
            f"📱 Phone: `{order['phone']}`\n"
            f"🌍 Country: {order['country']}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        try:
            await client.send_message(chat_id=LOG_GROUP, text=log_text)
        except Exception as e:
            print(f"[LOG] Failed to send logout log: {e}")

        await _edit(
            callback,
            f"✅ Session for `{order['phone']}` has been closed.\n\n"
            f"The order is now marked as complete.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 My Orders", callback_data="open_orders")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")]
            ])
        )

    except Exception as e:
        await _edit(callback, f"❌ Could not close session: `{e}`",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_orders")]]))
