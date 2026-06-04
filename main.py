from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from info import BOT_TOKEN, API_ID, API_HASH, ADMIN_ID

from handlers.user import (
    start, balance, buy,
    handle_message, button_handler
)
from handlers.admin import stats, add_bal, broadcast
from handlers.payment import payment_callback

app = Client(
    "otpbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# ── User commands ────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await start(client, message)


@app.on_message(filters.command("balance") & filters.private)
async def balance_handler(client, message):
    await balance(client, message)


@app.on_message(filters.command("buy") & filters.private)
async def buy_handler(client, message):
    await buy(client, message)


# ── Admin commands ───────────────────────────
@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client, message):
    await stats(client, message)


@app.on_message(filters.command("addbal") & filters.private)
async def addbal_handler(client, message):
    await add_bal(client, message)


@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(client, message):
    await broadcast(client, message)


# ── Message handler (for multi-step flow) ───
@app.on_message(
    filters.private & ~filters.command(
        ["start", "balance", "buy", "stats", "addbal", "broadcast"]
    )
)
async def message_handler(client, message):
    await handle_message(client, message)


# ── Callback handlers ────────────────────────
@app.on_callback_query(filters.regex("^(approve|reject)_"))
async def payment_cb(client, callback):
    await payment_callback(client, callback)


@app.on_callback_query(filters.regex("^(buy_otp|check_balance)$"))
async def button_cb(client, callback):
    await button_handler(client, callback)


if __name__ == "__main__":
    print("Bot started...")
    app.run()
