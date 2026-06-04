from pyrogram import Client, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import START_MESSAGE, RULES_TEXT, SUPPORT_TEXT, PROFILE_TEXT, HELP_TEXT, USER_HELP, ADMIN_HELP
from database import get_balance, get_user, get_user_orders, get_config, is_admin

user_states = {}


async def start(client: Client, message):
    """Handles both Message and CallbackQuery."""
    is_cb = isinstance(message, CallbackQuery)
    target = message.message if is_cb else message

    from handlers.fsub import check_fsub
    if not await check_fsub(client, target):
        return

    text = START_MESSAGE.format(name=message.from_user.first_name)
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
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def help_menu(client: Client, message):
    """Handles both Message and CallbackQuery."""
    is_cb = isinstance(message, CallbackQuery)
    target = message.message if is_cb else message

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User Commands", callback_data="help_user")],
        [InlineKeyboardButton("🔐 Admin Commands", callback_data="help_admin")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    if is_cb:
        await target.edit_text(HELP_TEXT, reply_markup=markup)
    else:
        await target.reply_text(HELP_TEXT, reply_markup=markup)


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
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(text, reply_markup=markup)


async def deposit_menu(client: Client, callback: CallbackQuery):
    config = get_config()
    upi_id = config.get("upi_id", "Not Set")
    upi_name = config.get("upi_name", "Not Set")
    upi_image = config.get("upi_image_file_id")

    text = (
        f"💳 **DEPOSIT FUNDS**\n\n"
        f"Pay via UPI to:\n"
        f"🏦 **UPI ID:** `{upi_id}`\n"
        f"After payment, enter the amount below:"
    )

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])

    # If admin has uploaded a UPI QR image, show it
    if upi_image:
        try:
            await callback.message.reply_photo(
                photo=upi_image,
                caption=text,
                reply_markup=markup
            )
            try:
                await callback.message.delete()
            except Exception:
                pass
        except Exception:
            await callback.message.edit_text(text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)

    user_states[callback.from_user.id] = {"step": "waiting_amount"}


async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id

    # Check Admin Interactive States first
    from handlers.admin import admin_states, handle_admin_msg
    if is_admin(user_id) and user_id in admin_states:
        await handle_admin_msg(client, message)
        return

    state = user_states.get(user_id)
    if not state:
        return

    step = state["step"]

    if step == "waiting_amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError
            user_states[user_id] = {"step": "waiting_ss", "amount": amount}
            await message.reply_text(
                f"✅ Amount: ₹{amount}\n\n📸 Now send your **payment screenshot** 👇"
            )
        except ValueError:
            await message.reply_text("❌ Invalid amount. Please enter a positive number (e.g., 100).")

    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Please send your payment screenshot as a **photo**.")
            return
        user_states[user_id].update({"step": "waiting_utr", "ss": message.photo.file_id})
        await message.reply_text("✅ Screenshot received!\n\n🔖 Now send your **UTR / Transaction ID** 👇")

    elif step == "waiting_utr":
        from database import add_transaction, utr_exists, get_config
        utr = message.text.strip()

        # Validate that UTR consists only of digits and falls within length rules (12 to 22 digits)
        if not utr.isdigit() or not (12 <= len(utr) <= 22):
            await message.reply_text(
                "⚠️ **Invalid UTR Format!**\n\n"
                "Your transaction UTR code must contain only numbers and be between **12 and 22 digits** long.\n\n"
                "💡 **Example of a valid UTR:**\n"
                "`202406041140` or `614207184925823`"
            )
            return

        if utr_exists(utr):
            await message.reply_text("❌ This UTR has already been submitted. Contact admin if this is an error.")
            return

        amount = state["amount"]
        ss = state["ss"]
        add_transaction(user_id, utr, amount, ss)
        config = get_config()

        caption = (
            f"💰 **New Payment Request**\n\n"
            f"👤 User: {message.from_user.first_name} (`{user_id}`)\n"
            f"💵 Amount: ₹{amount}\n"
            f"🔖 UTR: `{utr}`"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{utr}_{user_id}_{amount}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{utr}_{user_id}")
            ]
        ])

        from info import LOG_GROUP
        # Route verification message layout to specified LOG_GROUP channel instead
        try:
            await client.send_photo(LOG_GROUP, ss, caption=caption, reply_markup=markup)
        except Exception as e:
            print(f"Failed to route log verification message details to Log Group: {e}")

        await message.reply_text(
            "✅ **Payment submitted for verification!**\n\n"
            "You'll be notified once an admin reviews it.\n"
            "⏱️ Usually within a few minutes."
        )
        user_states.pop(user_id, None)


async def orders_menu(client: Client, callback: CallbackQuery):
    orders = get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text(
            "📦 **ORDERS**\n\n❌ You have no past orders.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
    else:
        buttons = []
        for ord in orders[:8]:
            status = "✅" if ord["status"] == "active" else "🔒"
            buttons.append([
                InlineKeyboardButton(
                    f"{status} {ord['country']} - {ord['phone']}",
                    callback_data=f"get_otp_{ord['order_id']}"
                )
            ])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await callback.message.edit_text("📦 **YOUR ORDERS**", reply_markup=InlineKeyboardMarkup(buttons))

