import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from info import BOT_TOKEN, API_ID, API_HASH
from database import is_admin

from handlers.user import (
    start, profile_menu, orders_menu,
    deposit_menu, help_menu, help_detail,
    handle_message
)
from handlers.shop import shop_menu, view_country_accounts, buy_account, get_otp_logic, logout_acc_logic
from handlers.admin import stats, add_bal, broadcast, manage_admins, set_config_cmd, add_acc_start
from handlers.payment import payment_callback

app = Client(
    "otpbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ── Commands ────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start_h(client, message):
    await start(client, message)

@app.on_message(filters.command("help") & filters.private)
async def help_h(client, message):
    await help_menu(client, message)

@app.on_message(filters.command(["stats", "addbal", "broadcast", "addadmin", "rmadmin", "setfsub", "setupi", "addacc", "recovery", "fa2", "sold", "login"]) & filters.private)
async def admin_cmds(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    cmd = message.command[0]
    if cmd == "stats":
        await stats(client, message)
    elif cmd == "addbal":
        await add_bal(client, message)
    elif cmd == "broadcast":
        await broadcast(client, message)
    elif cmd in ["addadmin", "rmadmin"]:
        await manage_admins(client, message)
    elif cmd in ["setfsub", "setupi", "recovery", "fa2"]:
        await set_config_cmd(client, message)
    elif cmd == "addacc":
        await add_acc_start(client, message)
    elif cmd == "sold":
        from handlers.admin import sold_accounts
        await sold_accounts(client, message)
    elif cmd == "login":
        from handlers.session import login_command
        await login_command(client, message)

# ── Message Handler ─────────────────────────
@app.on_message(filters.private & ~filters.command(["start", "help", "stats", "addbal", "broadcast", "addadmin", "rmadmin", "setfsub", "setupi", "addacc", "recovery", "fa2", "sold", "login"]))
async def msg_h(client, message):
    from handlers.session import session_states, handle_session_message
    from handlers.payment import payment_admin_states, handle_admin_rejection_reason

    # Priority 1: Check if admin is currently typing a payment rejection reason
    if message.from_user.id in payment_admin_states:
        await handle_admin_rejection_reason(client, message)
    
    # Priority 2: Check if admin is in a login session stage
    elif message.from_user.id in session_states:
        await handle_session_message(client, message)
        
    # Priority 3: Fallback to regular user message handling
    else:
        await handle_message(client, message)

# ── Callbacks ───────────────────────────────
@app.on_callback_query()
async def cb_h(client, callback: CallbackQuery):
    data = callback.data

    if data == "back_to_main":
        await start(client, callback)
    elif data == "open_shop":
        await shop_menu(client, callback)
    elif data == "open_deposit":
        await deposit_menu(client, callback)
    elif data == "open_profile":
        await profile_menu(client, callback)
    elif data == "open_orders":
        await orders_menu(client, callback)
    elif data == "open_help":
        await help_menu(client, callback)
    elif data in ["help_user", "help_admin"]:
        await help_detail(client, callback)
    elif data == "open_rules":
        from info import RULES_TEXT
        await callback.message.edit_text(
            RULES_TEXT,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
    elif data == "open_support":
        from info import SUPPORT_TEXT
        await callback.message.edit_text(
            SUPPORT_TEXT,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
    elif data.startswith("view_country_"):
        await view_country_accounts(client, callback)
    elif data.startswith("buy_acc_"):
        await buy_account(client, callback)
    elif data.startswith("get_otp_"):
        await get_otp_logic(client, callback)
    elif data.startswith("logout_acc_"):
        await logout_acc_logic(client, callback)
    elif data.startswith("approve_") or data.startswith("reject_"):
        await payment_callback(client, callback)
    elif data.startswith("setup_"):
        from handlers.session import handle_automation_callback
        await handle_automation_callback(client, callback)
    elif data == "set_upi_image":
        from handlers.admin import set_upi_image_start
        await set_upi_image_start(client, callback)


async def main():
    async with app:
        print("✅ Bot is running...")
        await asyncio.Event().wait()  # Run forever


if __name__ == "__main__":
    # Fix for Python 3.10+ / Heroku: explicitly create and set event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(main())
