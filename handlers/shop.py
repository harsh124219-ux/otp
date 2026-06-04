from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import (
    get_balance, deduct_balance, get_available_accounts,
    update_account_status, create_order, get_order, close_order, accounts_col
)
from info import API_ID, API_HASH


def mask_number(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return phone[:4] + "*" * (len(phone) - 7) + phone[-3:]


async def shop_menu(client: Client, message: Message):
    # Fix: If this function is triggered via a callback button, extract the message object safely
    if isinstance(message, CallbackQuery):
        message = message.message

    countries = accounts_col.distinct("country", {"status": "available"})

    if not countries:
        await message.edit_text(
            "🛒 **SHOP**\n\n❌ No accounts available at the moment. Check back later!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
        return

    buttons = []
    for country in sorted(countries):
        count = accounts_col.count_documents({"status": "available", "country": country})
        buttons.append([
            InlineKeyboardButton(f"🌍 {country} ({count} available)", callback_data=f"view_country_{country}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])

    await message.edit_text(
        "🛒 **SHOP — SELECT COUNTRY**\n\nChoose a country to see available accounts:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def view_country_accounts(client: Client, callback: CallbackQuery):
    country = callback.data.replace("view_country_", "")
    accounts = get_available_accounts(country)

    if not accounts:
        await callback.answer("No accounts available for this country.", show_alert=True)
        return

    text = f"🛒 **ACCOUNTS IN {country}**\n\n_Sorted: Expensive → Cheap_\n\n"
    buttons = []
    for acc in accounts:
        masked = mask_number(acc["phone"])
        buttons.append([
            InlineKeyboardButton(f"📱 {masked}  —  ₹{acc['price']}", callback_data=f"buy_acc_{acc['phone']}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back to Shop", callback_data="open_shop")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def buy_account(client: Client, callback: CallbackQuery):
    phone = callback.data.replace("buy_acc_", "")
    acc = accounts_col.find_one({"phone": phone, "status": "available"})

    if not acc:
        await callback.answer("⚠️ Account no longer available.", show_alert=True)
        return

    user_id = callback.from_user.id
    price = acc["price"]
    balance = get_balance(user_id)

    if balance < price:
        await callback.answer(f"❌ Insufficient balance! Required: ₹{price}", show_alert=True)
        return

    if deduct_balance(user_id, price):
        update_account_status(phone, "sold")
        order_id = create_order(user_id, phone, acc["session_string"], acc["country"], price)

        await callback.message.edit_text(
            f"✅ **Purchase Successful!**\n\n"
            f"🌍 Country: {acc['country']}\n"
            f"📱 Phone: `{phone}`\n"
            f"💰 Price: ₹{price}\n"
            f"🆔 Order ID: `{order_id}`\n\n"
            f"Tap below to fetch your OTP anytime.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Get OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
            ])
        )
    else:
        await callback.answer("❌ Error processing transaction. Try again.", show_alert=True)


async def get_otp_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("get_otp_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order["status"] == "closed":
        await callback.answer("This order is closed (account logged out).", show_alert=True)
        return

    await callback.answer("⏳ Fetching OTP...")

    try:
        user_client = Client(
            f"s_{order['phone']}",
            API_ID,
            API_HASH,
            session_string=order["session_string"],
            in_memory=True
        )
        await user_client.connect()

        otp = "No OTP found yet."
        async for m in user_client.get_chat_history(777000, limit=1):
            otp = m.text if m.text else "Non-text message received."

        await user_client.disconnect()

        await callback.message.reply_text(
            f"📩 **OTP FOR** `{order['phone']}`\n\n`{otp}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh OTP", callback_data=f"get_otp_{order_id}")],
                [InlineKeyboardButton("🚪 Logout Account", callback_data=f"logout_acc_{order_id}")]
            ])
        )
    except Exception as e:
        await callback.message.reply_text(f"❌ Error fetching OTP: `{str(e)}`")


async def logout_acc_logic(client: Client, callback: CallbackQuery):
    order_id = callback.data.replace("logout_acc_", "")
    order = get_order(order_id)

    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    try:
        user_client = Client(
            f"s_{order['phone']}",
            API_ID,
            API_HASH,
            session_string=order["session_string"],
            in_memory=True
        )
        await user_client.connect()
        await user_client.log_out()
        close_order(order_id)
        await callback.message.edit_text(
            f"✅ Successfully logged out from `{order['phone']}`.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
    except Exception as e:
        await callback.answer(f"Error logging out: {str(e)}", show_alert=True)
