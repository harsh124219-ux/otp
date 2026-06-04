from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from info import BOT_TOKEN, API_ID, API_HASH, ADMIN_ID

from handlers.user import (
    start, profile_menu, orders_menu, 
    rules_menu, support_menu, deposit_menu,
    handle_message
)
from handlers.shop import shop_menu, buy_country, get_otp_logic, logout_acc_logic
from handlers.admin import stats, add_bal, broadcast
from handlers.payment import payment_callback

app = Client(
    "otpbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ── Command Handlers ────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await start(client, message)

@app.on_message(filters.command("stats") & filters.private)
async def stats_h(client, message):
    await stats(client, message)

@app.on_message(filters.command("addbal") & filters.private)
async def addbal_h(client, message):
    await add_bal(client, message)

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_h(client, message):
    await broadcast(client, message)

# ── Message Handler (Deposits) ──────────────
@app.on_message(filters.private & ~filters.command(["start", "stats", "addbal", "broadcast"]))
async def msg_handler(client, message):
    await handle_message(client, message)

# ── Callback Handlers ───────────────────────
@app.on_callback_query()
async def cb_handler(client, callback: CallbackQuery):
    data = callback.data

    # Main Menu & Navigation
    if data == "back_to_main":
        await start(client, callback)
    elif data == "open_shop":
        await shop_menu(client, callback.message)
    elif data == "open_deposit":
        await deposit_menu(client, callback)
    elif data == "open_profile":
        await profile_menu(client, callback)
    elif data == "open_orders":
        await orders_menu(client, callback)
    elif data == "open_rules":
        await rules_menu(client, callback)
    elif data == "open_support":
        await support_menu(client, callback)

    # Shop Logic
    elif data.startswith("buy_country_"):
        await buy_country(client, callback)
    elif data.startswith("get_otp_"):
        await get_otp_logic(client, callback)
    elif data.startswith("logout_acc_"):
        await logout_acc_logic(client, callback)

    # Payment Logic (Admin)
    elif data.startswith("approve_") or data.startswith("reject_"):
        await payment_callback(client, callback)

if __name__ == "__main__":
    print("Bot started...")
    app.run()
