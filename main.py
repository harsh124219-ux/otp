from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from info import BOT_TOKEN, API_ID, API_HASH, ADMIN_ID

from handlers.user import (
    start, balance, buy, history,
    handle_message, button_handler
)
from handlers.admin import stats, add_bal, broadcast
from handlers.payment import payment_callback
from handlers.session import login_command, logout_command

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


@app.on_message(filters.command("history") & filters.private)
async def history_handler(client, message):
    await history(client, message)


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


@app.on_message(filters.command("login") & filters.private)
async def login_handler(client, message):
    await login_command(client, message)


@app.on_message(filters.command("logout") & filters.private)
async def logout_handler(client, message):
    await logout_command(client, message)


# ── Message handler (for multi-step flow) ───
@app.on_message(
    filters.private & ~filters.command(
        ["start", "balance", "buy", "history", "stats", "addbal", "broadcast", "login", "logout"]
    )
)
async def message_handler(client, message):
    await handle_message(client, message)


# ── Callback handlers ────────────────────────
@app.on_callback_query(filters.regex("^(approve|reject)_"))
async def payment_cb(client, callback):
    await payment_callback(client, callback)


@app.on_callback_query(filters.regex("^(buy_otp_start|check_balance|buy_otp|view_history)$"))
async def button_cb(client, callback):
    await button_handler(client, callback)


if __name__ == "__main__":
    print("Bot started...")
    app.run()
