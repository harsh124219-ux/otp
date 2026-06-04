from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from info import UPI_ID, UPI_NAME, START_MESSAGE, OTP_PRICE
from database import get_balance, get_user, get_sales_history

# Tracks users mid-flow: {user_id: {"step": ..., "amount": ...}}
user_states = {}


async def start(client: Client, message: Message):
    await message.reply_text(
        START_MESSAGE.format(
            name=message.from_user.first_name,
            price=OTP_PRICE,
            upi=UPI_ID
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy OTP", callback_data="buy_otp_start")],
            [InlineKeyboardButton("💰 Balance", callback_data="check_balance")],
            [InlineKeyboardButton("📜 History", callback_data="view_history")]
        ])
    )


async def balance(client: Client, message: Message):
    bal = get_balance(message.from_user.id)
    await message.reply_text(f"💰 Your balance: ₹{bal}")


async def buy(client: Client, message: Message):
    await message.reply_text(
        f"💳 **Add Balance**\n\n"
        f"Send payment to:\n"
        f"🏦 UPI ID: `{UPI_ID}`\n"
        f"👤 Name: {UPI_NAME}\n\n"
        f"Enter the amount you want to add (e.g. `100`):",
    )
    user_states[message.from_user.id] = {"step": "waiting_amount"}


async def history(client: Client, message: Message):
    user_id = message.from_user.id
    sales = get_sales_history(user_id)
    
    if not sales:
        await message.reply_text("📜 You haven't purchased any OTPs yet.")
        return

    text = "📜 **Your Purchase History**\n\n"
    for sale in sales:
        time = sale["timestamp"].strftime("%d-%m %H:%M")
        text += f"📅 {time} | ₹{sale['price']}\n`{sale['content'][:50]}...`\n\n"
    
    await message.reply_text(text)


async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    # Check if this is for session login (Admin only)
    from handlers.session import session_states, handle_session_message
    from info import ADMIN_ID
    if user_id == ADMIN_ID and user_id in session_states:
        await handle_session_message(client, message)
        return

    if not state:
        return

    step = state.get("step")

    # Step 1: User enters amount
    if step == "waiting_amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ Invalid amount. Please enter a valid number.")
            return

        user_states[user_id] = {"step": "waiting_ss", "amount": amount}
        await message.reply_text(
            f"✅ Amount: ₹{amount}\n\n"
            f"📲 Pay ₹{amount} to UPI: `{UPI_ID}`\n\n"
            f"After paying, send the **screenshot** of payment 👇",
        )

    # Step 2: User sends screenshot
    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Please send a **photo/screenshot** of your payment.")
            return

        ss_file_id = message.photo.file_id
        user_states[user_id] = {
            "step": "waiting_utr",
            "amount": state["amount"],
            "ss_file_id": ss_file_id
        }
        await message.reply_text(
            "✅ Screenshot received!\n\n"
            "Now send your **UTR / Transaction ID** 👇\n"
            "(12-digit number found in payment receipt)"
        )

    # Step 3: User sends UTR
    elif step == "waiting_utr":
        from database import add_transaction, utr_exists
        from info import LOG_GROUP

        utr = message.text.strip()

        if len(utr) < 6:
            await message.reply_text("❌ Invalid UTR. Please check and try again.")
            return

        if utr_exists(utr):
            await message.reply_text(
                "⚠️ This UTR has already been submitted.\n"
                "If you think this is a mistake, contact the owner."
            )
            user_states.pop(user_id, None)
            return

        amount = state["amount"]
        ss_file_id = state["ss_file_id"]

        # Save to DB
        add_transaction(user_id, utr, amount, ss_file_id)

        # Send to log group
        user_info = message.from_user
        caption = (
            f"💰 **New Payment Request**\n\n"
            f"👤 User: [{user_info.first_name}](tg://user?id={user_id})\n"
            f"🆔 User ID: `{user_id}`\n"
            f"💵 Amount: ₹{amount}\n"
            f"🔖 UTR: `{utr}`\n"
            f"📅 Time: {__import__('datetime').datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )

        await client.send_photo(
            chat_id=LOG_GROUP,
            photo=ss_file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"approve_{utr}_{user_id}_{amount}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"reject_{utr}_{user_id}"
                    )
                ]
            ])
        )

        await message.reply_text(
            "✅ **Payment submitted for verification!**\n\n"
            "⏳ Admin will verify and credit your balance shortly.\n"
            "You'll receive a notification once approved."
        )

        user_states.pop(user_id, None)


async def button_handler(client: Client, callback: CallbackQuery):
    await callback.answer()
    data = callback.data
    
    if data == "buy_otp_start":
        from handlers.otp import buy_otp_handler
        await buy_otp_handler(client, callback)
    elif data == "check_balance":
        bal = get_balance(callback.from_user.id)
        await callback.message.reply_text(f"💰 Your balance: ₹{bal}")
    elif data == "buy_otp": # From main menu
        await buy(client, callback.message)
    elif data == "view_history":
        await history(client, callback.message)
