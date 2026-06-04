from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import START_MESSAGE, RULES_TEXT, SUPPORT_TEXT, PROFILE_TEXT, HELP_TEXT, USER_HELP, ADMIN_HELP
from database import get_balance, get_user, get_user_orders, get_config, is_admin

user_states = {}

async def start(client: Client, message: Message):
    is_cb = isinstance(message, CallbackQuery)
    target = message.message if is_cb else message
    user_id = message.from_user.id

    # Check FSub
    from handlers.fsub import check_fsub
    if not await check_fsub(client, target if not is_cb else message):
        return

    text = START_MESSAGE.format(name=message.from_user.first_name)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Shop", callback_data="open_shop"), InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("👤 Profile", callback_data="open_profile"), InlineKeyboardButton("📦 Orders", callback_data="open_orders")],
        [InlineKeyboardButton("🛟 Support", callback_data="open_support"), InlineKeyboardButton("📋 Rules", callback_data="open_rules")],
        [InlineKeyboardButton("📖 Help", callback_data="open_help")]
    ])

    if is_cb: await target.edit_text(text, reply_markup=markup)
    else: await target.reply_text(text, reply_markup=markup)

async def help_menu(client: Client, callback: CallbackQuery):
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User Commands", callback_data="help_user")],
        [InlineKeyboardButton("🔐 Admin Commands", callback_data="help_admin")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(HELP_TEXT, reply_markup=markup)

async def help_detail(client: Client, callback: CallbackQuery):
    is_admin_help = callback.data == "help_admin"
    if is_admin_help and not is_admin(callback.from_user.id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = ADMIN_HELP if is_admin_help else USER_HELP
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_help")]])
    await callback.message.edit_text(text, reply_markup=markup)

async def profile_menu(client: Client, callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    orders = get_user_orders(callback.from_user.id)
    text = PROFILE_TEXT.format(
        name=callback.from_user.first_name,
        balance=user.get("balance", 0),
        total_spent=user.get("total_spent", 0),
        total_purchases=len(orders)
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=markup)

async def deposit_menu(client: Client, callback: CallbackQuery):
    config = get_config()
    await callback.message.edit_text(
        f"💳 **DEPOSIT FUNDS**\n\nPay to:\n🏦 UPI ID: `{config['upi_id']}`\n👤 Name: {config['upi_name']}\n\n"
        "Enter amount to add (e.g. 100):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
    )
    user_states[callback.from_user.id] = {"step": "waiting_amount"}

async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check Admin Interactive States
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
            await message.reply_text(f"✅ Amount: ₹{amount}\n\nSend payment screenshot 👇")
        except: await message.reply_text("❌ Invalid amount.")

    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Send screenshot photo.")
            return
        user_states[user_id].update({"step": "waiting_utr", "ss": message.photo.file_id})
        await message.reply_text("✅ Send UTR / Transaction ID 👇")

    elif step == "waiting_utr":
        from database import add_transaction, utr_exists, get_config
        utr = message.text.strip()
        if len(utr) < 6 or utr_exists(utr):
            await message.reply_text("❌ Invalid or duplicate UTR.")
            return
        
        amount, ss = state["amount"], state["ss"]
        add_transaction(user_id, utr, amount, ss)
        config = get_config()
        
        # Notify Admins (Primary admin and others)
        caption = f"💰 **New Payment**\n👤 {message.from_user.first_name} ({user_id})\n💵 ₹{amount}\n🔖 UTR: `{utr}`"
        for admin in config["admins"]:
            try:
                await client.send_photo(admin, ss, caption=caption, reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{utr}_{user_id}_{amount}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"reject_{utr}_{user_id}")]
                ]))
            except: pass
        await message.reply_text("✅ Submitted for verification!")
        user_states.pop(user_id, None)

async def orders_menu(client: Client, callback: CallbackQuery):
    orders = get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text("📦 **ORDERS**\n\n❌ NO PAST ORDERS FOUND!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]))
    else:
        buttons = []
        for ord in orders[:8]:
            status = "✅" if ord["status"] == "active" else "🔒"
            buttons.append([InlineKeyboardButton(f"{status} {ord['country']} - {ord['phone']}", callback_data=f"get_otp_{ord['order_id']}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await callback.message.edit_text("📦 **YOUR ORDERS**", reply_markup=InlineKeyboardMarkup(buttons))
