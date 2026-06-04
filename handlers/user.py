from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import START_MESSAGE, PROFILE_TEXT, HELP_TEXT, USER_HELP, ADMIN_HELP
from database import get_user, get_user_orders, get_config, is_admin

user_states = {}

async def edit_or_reply(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    """Safely edit the existing message or send a new one if it fails (e.g., if deleted)."""
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.reply(text, reply_markup=markup)

async def start(client: Client, message):
    """Handles both Message and CallbackQuery."""
    is_cb = isinstance(message, CallbackQuery)
    target = message.message if is_cb else message
    
    from handlers.fsub import check_fsub
    if not await check_fsub(client, target):
        return

    text = START_MESSAGE.format(name=target.chat.first_name)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Shop", callback_data="open_shop"),
         InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("👤 Profile", callback_data="open_profile"),
         InlineKeyboardButton("📦 Orders", callback_data="open_orders")],
        [InlineKeyboardButton("🛟 Support", callback_data="open_support"),
         InlineKeyboardButton("📋 Rules", callback_data="open_rules")],
        [InlineKeyboardButton("📖 Help", callback_data="open_help")]
    ])

    if is_cb:
        await edit_or_reply(message, text, markup)
    else:
        await target.reply_text(text, reply_markup=markup)

async def help_menu(client: Client, message):
    is_cb = isinstance(message, CallbackQuery)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User Commands", callback_data="help_user")],
        [InlineKeyboardButton("🔐 Admin Commands", callback_data="help_admin")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    if is_cb:
        await edit_or_reply(message, HELP_TEXT, markup)
    else:
        await message.reply_text(HELP_TEXT, reply_markup=markup)

async def help_detail(client: Client, callback: CallbackQuery):
    is_admin_help = callback.data == "help_admin"
    if is_admin_help and not is_admin(callback.from_user.id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return

    text = ADMIN_HELP if is_admin_help else USER_HELP
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_help")]])
    await edit_or_reply(callback, text, markup)

async def profile_menu(client: Client, callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    orders = get_user_orders(callback.from_user.id)
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
    await edit_or_reply(callback, text, markup)

async def deposit_menu(client: Client, callback: CallbackQuery):
    config = get_config()
    upi_id = config.get("upi_id", "Not Set")
    upi_image = config.get("upi_image_file_id")

    text = (
        f"💳 **DEPOSIT FUNDS**\n\n"
        f"Pay via UPI to:\n"
        f"🏦 **UPI ID:** `{upi_id}`\n\n"
        f"After payment, please send the transaction screenshot.\n"
        f"Enter the amount to proceed."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_deposit")]])

    if upi_image:
        try:
            await callback.message.reply_photo(photo=upi_image, caption=text, reply_markup=markup)
        except Exception:
            await callback.message.reply(text, reply_markup=markup)
    else:
        await callback.message.reply(text, reply_markup=markup)

    try:
        await callback.message.delete()
    except Exception:
        pass
    user_states[callback.from_user.id] = {"step": "waiting_amount"}
    await callback.answer()

async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    from handlers.admin import admin_states, handle_admin_msg
    if is_admin(user_id) and user_id in admin_states:
        await handle_admin_msg(client, message)
        return

    state = user_states.get(user_id)
    if not state: return

    step = state["step"]
    if step == "waiting_amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0: raise ValueError
            user_states[user_id] = {"step": "waiting_ss", "amount": amount}
            await message.reply_text(f"✅ Amount: ₹{amount}\n\n📸 Now send your **payment screenshot** 👇")
        except ValueError:
            await message.reply_text("❌ Invalid amount. Please enter a positive number (e.g., 100).")

    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Please send your payment screenshot as a **photo**.")
            return
        user_states[user_id].update({"step": "waiting_utr", "ss": message.photo.file_id})
        await message.reply_text("✅ Screenshot received!\n\n🔖 Now send your **UTR / Transaction ID** 👇")

    elif step == "waiting_utr":
        from database import add_transaction, utr_exists
        utr = message.text.strip()
        if not utr.isdigit() or not (12 <= len(utr) <= 22):
            await message.reply_text("⚠️ **Invalid UTR Format!** Use 12-22 digits.")
            return
        if utr_exists(utr):
            await message.reply_text("❌ This UTR has already been submitted.")
            return

        amount, ss = state["amount"], state["ss"]
        add_transaction(user_id, utr, amount, ss)
        
        caption = f"💰 **New Payment Request**\n\n👤 User: {message.from_user.first_name} (`{user_id}`)\n💵 Amount: ₹{amount}\n🔖 UTR: `{utr}`"
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{utr}_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{utr}_{user_id}")
        ]])

        from info import LOG_GROUP
        try:
            await client.send_photo(LOG_GROUP, ss, caption=caption, reply_markup=markup)
        except Exception as e:
            print(f"Log Error: {e}")

        await message.reply_text("✅ **Payment submitted for verification!**")
        user_states.pop(user_id, None)

async def orders_menu(client: Client, callback: CallbackQuery):
    orders = get_user_orders(callback.from_user.id)
    markup_back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    
    if not orders:
        await edit_or_reply(callback, "📦 **ORDERS**\n\n❌ You have no past orders.", markup_back)
    else:
        buttons = [[InlineKeyboardButton(f"{'✅' if o['status'] == 'active' else '🔒'} {o['country']} - {o['phone']}", 
                    callback_data=f"get_otp_{o['order_id']}")] for o in orders[:8]]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await edit_or_reply(callback, "📦 **YOUR ORDERS**", InlineKeyboardMarkup(buttons))
