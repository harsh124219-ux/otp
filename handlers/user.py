from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from info import (
    UPI_ID, UPI_NAME, START_MESSAGE, 
    RULES_TEXT, SUPPORT_TEXT, PROFILE_TEXT
)
from database import get_balance, get_user, get_user_orders

# Tracks users mid-flow for deposits
user_states = {}

async def start(client: Client, message: Message):
    # Determine if it's a message or callback
    is_callback = isinstance(message, CallbackQuery)
    target = message.message if is_callback else message
    name = message.from_user.first_name if is_callback else message.from_user.first_name

    text = START_MESSAGE.format(name=name)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Shop", callback_data="open_shop"), InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("👤 Profile", callback_data="open_profile"), InlineKeyboardButton("📦 Orders", callback_data="open_orders")],
        [InlineKeyboardButton("🛟 Support", callback_data="open_support"), InlineKeyboardButton("📋 Rules", callback_data="open_rules")]
    ])

    if is_callback:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)

async def profile_menu(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    orders = get_user_orders(user_id)
    
    text = PROFILE_TEXT.format(
        name=callback.from_user.first_name,
        balance=user.get("balance", 0),
        total_spent=user.get("total_spent", 0),
        total_purchases=len(orders)
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(text, reply_markup=markup)

async def orders_menu(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = get_user_orders(user_id)
    
    if not orders:
        text = "📦 **ORDERS**\n\n❌ NO PAST ORDERS FOUND!"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    else:
        text = "📦 **YOUR RECENT ORDERS**\n\nSelect an order to get OTP:"
        buttons = []
        # Show last 5 active orders
        for ord in orders[:5]:
            status = "✅" if ord["status"] == "active" else "🔒"
            buttons.append([InlineKeyboardButton(f"{status} {ord['country']} - {ord['phone']}", callback_data=f"get_otp_{ord['order_id']}")])
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        markup = InlineKeyboardMarkup(buttons)

    await callback.message.edit_text(text, reply_markup=markup)

async def rules_menu(client: Client, callback: CallbackQuery):
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    await callback.message.edit_text(RULES_TEXT, reply_markup=markup)

async def support_menu(client: Client, callback: CallbackQuery):
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    await callback.message.edit_text(SUPPORT_TEXT, reply_markup=markup)

async def deposit_menu(client: Client, callback: CallbackQuery):
    await callback.message.edit_text(
        f"💳 **DEPOSIT FUNDS**\n\n"
        f"Send payment to:\n"
        f"🏦 UPI ID: `{UPI_ID}`\n"
        f"👤 Name: {UPI_NAME}\n\n"
        f"Enter the amount you want to add (e.g. `100`):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    )
    user_states[callback.from_user.id] = {"step": "waiting_amount"}

async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state: return

    step = state.get("step")

    if step == "waiting_amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0: raise ValueError
        except ValueError:
            await message.reply_text("❌ Invalid amount. Please enter a valid number.")
            return

        user_states[user_id] = {"step": "waiting_ss", "amount": amount}
        await message.reply_text(
            f"✅ Amount: ₹{amount}\n\n"
            f"📲 Pay ₹{amount} to UPI: `{UPI_ID}`\n\n"
            f"After paying, send the **screenshot** of payment 👇",
        )

    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Please send a **photo/screenshot** of your payment.")
            return

        ss_file_id = message.photo.file_id
        user_states[user_id] = {"step": "waiting_utr", "amount": state["amount"], "ss_file_id": ss_file_id}
        await message.reply_text("✅ Screenshot received!\n\nNow send your **UTR / Transaction ID** 👇")

    elif step == "waiting_utr":
        from database import add_transaction, utr_exists
        from info import LOG_GROUP
        utr = message.text.strip()

        if len(utr) < 6:
            await message.reply_text("❌ Invalid UTR.")
            return

        if utr_exists(utr):
            await message.reply_text("⚠️ Already submitted.")
            user_states.pop(user_id, None)
            return

        amount, ss_file_id = state["amount"], state["ss_file_id"]
        add_transaction(user_id, utr, amount, ss_file_id)

        # Log to Admin
        caption = f"💰 **Payment Request**\n👤 User: {message.from_user.first_name}\n🆔 ID: `{user_id}`\n💵 Amount: ₹{amount}\n🔖 UTR: `{utr}`"
        await client.send_photo(
            chat_id=LOG_GROUP,
            photo=ss_file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{utr}_{user_id}_{amount}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_{utr}_{user_id}")]
            ])
        )

        await message.reply_text("✅ **Payment submitted!** Admin will verify shortly.")
        user_states.pop(user_id, None)
