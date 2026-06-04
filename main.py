from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
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
async def start_h(client, message): await start(client, message)

@app.on_message(filters.command("help") & filters.private)
async def help_h(client, message):
    await help_menu(client, CallbackQuery(client, message.from_user, message=message, data="open_help"))

@app.on_message(filters.command(["stats", "addbal", "broadcast", "addadmin", "rmadmin", "setfsub", "setupi", "addacc"]) & filters.private)
async def admin_cmds(client, message: Message):
    if not is_admin(message.from_user.id): return
    cmd = message.command[0]
    if cmd == "stats": await stats(client, message)
    elif cmd == "addbal": await add_bal(client, message)
    elif cmd == "broadcast": await broadcast(client, message)
    elif cmd in ["addadmin", "rmadmin"]: await manage_admins(client, message)
    elif cmd in ["setfsub", "setupi"]: await set_config_cmd(client, message)
    elif cmd == "addacc": await add_acc_start(client, message)

# ── Message Handler ─────────────────────────
@app.on_message(filters.private & ~filters.command(["start", "help", "stats", "addbal", "broadcast", "addadmin", "rmadmin", "setfsub", "setupi", "addacc"]))
async def msg_h(client, message): await handle_message(client, message)

# ── Callbacks ───────────────────────────────
@app.on_callback_query()
async def cb_h(client, callback: CallbackQuery):
    data = callback.data
    if data == "back_to_main": await start(client, callback)
    elif data == "open_shop": await shop_menu(client, callback.message)
    elif data == "open_deposit": await deposit_menu(client, callback)
    elif data == "open_profile": await profile_menu(client, callback)
    elif data == "open_orders": await orders_menu(client, callback)
    elif data == "open_help": await help_menu(client, callback)
    elif data in ["help_user", "help_admin"]: await help_detail(client, callback)
    elif data == "open_rules":
        from info import RULES_TEXT
        await callback.message.edit_text(RULES_TEXT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]))
    elif data == "open_support":
        from info import SUPPORT_TEXT
        await callback.message.edit_text(SUPPORT_TEXT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]))
    
    # Shop & Account Logic
    elif data.startswith("view_country_"): await view_country_accounts(client, callback)
    elif data.startswith("buy_acc_"): await buy_account(client, callback)
    elif data.startswith("get_otp_"): await get_otp_logic(client, callback)
    elif data.startswith("logout_acc_"): await logout_acc_logic(client, callback)
    
    # Payment (Admin)
    elif data.startswith("approve_") or data.startswith("reject_"): await payment_callback(client, callback)

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
