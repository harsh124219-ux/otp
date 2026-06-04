from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import START_MESSAGE, PROFILE_TEXT, HELP_TEXT, USER_HELP, ADMIN_HELP
from database import get_user, get_user_orders, get_config, is_admin

user_states = {}


# ─────────────────────────────────────────────────────────────
#  Core Navigation Helper
# ─────────────────────────────────────────────────────────────

async def safe_edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    """
    Always tries to EDIT the existing message.
    Falls back to replying only if edit truly fails (e.g. message was deleted).
    This keeps the chat clean — no new messages on navigation.
    """
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.reply_text(text, reply_markup=markup)


def _main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Shop",    callback_data="open_shop"),
         InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("👤 Profile", callback_data="open_profile"),
         InlineKeyboardButton("📦 Orders",  callback_data="open_orders")],
        [InlineKeyboardButton("🛟 Support", callback_data="open_support"),
         InlineKeyboardButton("📋 Rules",   callback_data="open_rules")],
        [InlineKeyboardButton("📖 Help",    callback_data="open_help")]
    ])


# ─────────────────────────────────────────────────────────────
#  /start  &  back_to_main
# ─────────────────────────────────────────────────────────────

async def start(client: Client, update):
    """
    Handles /start (Message) and back_to_main (CallbackQuery).
    FSub is checked here so it covers both paths.
    """
    is_cb = isinstance(update, CallbackQuery)
    # For fsub check we need the real Message object
    message_obj = update.message if is_cb else update

    from handlers.fsub import check_fsub
    if not await check_fsub(client, message_obj):
        return

    first_name = message_obj.chat.first_name or "there"
    text   = START_MESSAGE.format(name=first_name)
    markup = _main_menu_markup()

    if is_cb:
        await safe_edit(update, text, markup)
    else:
        await message_obj.reply_text(text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────
#  Help
# ─────────────────────────────────────────────────────────────

async def help_menu(client: Client, update):
    is_cb = isinstance(update, CallbackQuery)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User Commands",  callback_data="help_user")],
        [InlineKeyboardButton("🔐 Admin Commands", callback_data="help_admin")],
        [InlineKeyboardButton("🔙 Back",           callback_data="back_to_main")]
    ])
    if is_cb:
        await safe_edit(update, HELP_TEXT, markup)
    else:
        await update.reply_text(HELP_TEXT, reply_markup=markup)


async def help_detail(client: Client, callback: CallbackQuery):
    is_admin_help = callback.data == "help_admin"
    if is_admin_help and not is_admin(callback.from_user.id):
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    text   = ADMIN_HELP if is_admin_help else USER_HELP
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_help")]])
    await safe_edit(callback, text, markup)


# ─────────────────────────────────────────────────────────────
#  Profile
# ─────────────────────────────────────────────────────────────

async def profile_menu(client: Client, callback: CallbackQuery):
    user   = get_user(callback.from_user.id)
    orders = get_user_orders(callback.from_user.id)
    text   = PROFILE_TEXT.format(
        name=callback.from_user.first_name,
        balance=user.get("balance", 0) if user else 0,
        total_spent=user.get("total_spent", 0) if user else 0,
        total_purchases=len(orders)
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
        [InlineKeyboardButton("🔙 Back",    callback_data="back_to_main")]
    ])
    await safe_edit(callback, text, markup)


# ─────────────────────────────────────────────────────────────
#  Deposit
# ─────────────────────────────────────────────────────────────

async def deposit_menu(client: Client, callback: CallbackQuery):
    """
    Deposit is intentionally a NEW message because it may include a UPI photo.
    We delete the old message to keep chat clean, then send fresh.
    """
    config    = get_config()
    upi_id    = config.get("upi_id", "Not Set")
    upi_name  = config.get("upi_name", "")
    upi_image = config.get("upi_image_file_id")

    text = (
        f"💳 **DEPOSIT FUNDS**\n\n"
        f"Pay via UPI to:\n"
        f"🏦 **UPI ID:** `{upi_id}`\n"
        f"👤 **Name:** {upi_name}\n\n"
        f"After payment:\n"
        f"1️⃣ Type the **amount** you paid (e.g. `200`)\n"
        f"2️⃣ Send your **payment screenshot**\n"
        f"3️⃣ Send the **UTR / Transaction ID**"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deposit")]
    ])

    # Delete the old navigation message first
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send fresh (potentially with photo)
    if upi_image:
        try:
            await callback.message.reply_photo(
                photo=upi_image, caption=text, reply_markup=markup
            )
        except Exception:
            await callback.message.reply_text(text, reply_markup=markup)
    else:
        await callback.message.reply_text(text, reply_markup=markup)

    user_states[callback.from_user.id] = {"step": "waiting_amount"}
    await callback.answer()


# ─────────────────────────────────────────────────────────────
#  Orders
# ─────────────────────────────────────────────────────────────

async def orders_menu(client: Client, callback: CallbackQuery):
    orders = get_user_orders(callback.from_user.id)
    back   = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])

    if not orders:
        await safe_edit(callback, "📦 **MY ORDERS**\n\n❌ You have no orders yet.", back)
        return

    buttons = []
    for o in orders[:8]:
        status_icon = "✅" if o["status"] == "active" else "🔒"
        label = f"{status_icon} {o['country']} — {o['phone']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"get_otp_{o['order_id']}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
    await safe_edit(callback, "📦 **MY ORDERS**\n\nTap an order to fetch OTP:", InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────
#  Deposit Message Flow
# ─────────────────────────────────────────────────────────────

async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id

    # Admin flow takes priority
    from handlers.admin import admin_states, handle_admin_msg
    if is_admin(user_id) and user_id in admin_states:
        await handle_admin_msg(client, message)
        return

    state = user_states.get(user_id)
    if not state:
        return

    step = state["step"]

    # ── Step 1: Amount ─────────────────────────────────────────
    if step == "waiting_amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError
            user_states[user_id] = {"step": "waiting_ss", "amount": amount}
            await message.reply_text(
                f"✅ Amount set: ₹{amount}\n\n"
                f"📸 Now send your **payment screenshot** as a photo:"
            )
        except ValueError:
            await message.reply_text("❌ Invalid amount. Please enter a positive number (e.g. `200`).")

    # ── Step 2: Screenshot ─────────────────────────────────────
    elif step == "waiting_ss":
        if not message.photo:
            await message.reply_text("📸 Please send your payment screenshot as a **photo**.")
            return
        user_states[user_id].update({"step": "waiting_utr", "ss": message.photo.file_id})
        await message.reply_text(
            "✅ Screenshot received!\n\n"
            "🔖 Now send your **UTR / Transaction ID** (12–22 digits):"
        )

    # ── Step 3: UTR ────────────────────────────────────────────
    elif step == "waiting_utr":
        from database import add_transaction, utr_exists
        utr = message.text.strip()

        if not utr.isdigit() or not (12 <= len(utr) <= 22):
            await message.reply_text(
                "⚠️ **Invalid UTR Format!**\n\n"
                "UTR must be 12–22 digits only (no spaces or letters)."
            )
            return
        if utr_exists(utr):
            await message.reply_text(
                "❌ This UTR has already been submitted. "
                "Please check your transaction details."
            )
            return

        amount = state["amount"]
        ss     = state["ss"]
        add_transaction(user_id, utr, amount, ss)

        caption = (
            f"💰 **New Payment Request**\n\n"
            f"👤 User: {message.from_user.first_name} (`{user_id}`)\n"
            f"💵 Amount: ₹{amount}\n"
            f"🔖 UTR: `{utr}`"
        )
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{utr}_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{utr}_{user_id}")
        ]])

        from info import LOG_GROUP
        try:
            await client.send_photo(LOG_GROUP, ss, caption=caption, reply_markup=markup)
        except Exception as e:
            print(f"[LOG] Payment log error: {e}")

        await message.reply_text(
            "✅ **Payment submitted for verification!**\n\n"
            "You will be notified once an admin approves it."
        )
        user_states.pop(user_id, None)
