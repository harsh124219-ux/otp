import asyncio
import logging
import sys
import traceback
import os
import pyrogram
import aiohttp
import pyrogram.raw.functions.updates
from pyrogram import Client, filters, idle
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Update
from info import BOT_TOKEN, API_ID, API_HASH
from database import is_admin, init_db

from aiohttp import web

async def health(request):
    return web.Response(text="OK")

async def start_web():
    from aiohttp import web
    app_web = web.Application()
    app_web.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Web server started on port {port}")
    
# ── Robust logging to ensure visibility in all environments
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("OTPOceanBot")
# Set pyrogram to INFO to see connection events
logging.getLogger("pyrogram").setLevel(logging.INFO)

# ── Handler imports with startup diagnostics ─────────────────
try:
    from handlers.user import (
        start, profile_menu, orders_menu,
        deposit_menu, help_menu, help_detail,
        handle_message, user_states
    )
    logger.info("✅ handlers.user loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.user failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from handlers.shop import (
        shop_menu, sort_options_menu, view_country_accounts,
        buy_account, get_otp_logic, logout_acc_logic
    )
    logger.info("✅ handlers.shop loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.shop failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from handlers.admin import (
        stats, add_bal, broadcast, manage_admins,
        set_config_cmd, add_acc_start, sold_accounts,
        set_upi_image_start
    )
    logger.info("✅ handlers.admin loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.admin failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from handlers.payment import payment_callback
    logger.info("✅ handlers.payment loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.payment failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from handlers.fsub import recheck_fsub_callback
    logger.info("✅ handlers.fsub loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.fsub failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

try:
    import handlers.session as _session_check  # noqa: F401
    logger.info("✅ handlers.session loaded")
except Exception as _e:
    logger.error(f"❌ FATAL: handlers.session failed to load: {_e}")
    traceback.print_exc()
    sys.exit(1)

_clean_token = BOT_TOKEN.strip()

# Use a specific session name to avoid conflicts if multiple instances are running
app = Client(
    "otp_ocean_main",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=_clean_token,
    max_concurrent_transmissions=3,
)

# ─────────────────────────────────────────────────────────────
#  Heartbeat & Diagnostic Tasks
# ─────────────────────────────────────────────────────────────

async def heartbeat():
    """Periodically logs that the bot is still alive and connected."""
    while True:
        try:
            if app.is_connected:
                me = await app.get_me()
                logger.info(f"💓 HEARTBEAT: Bot @{me.username} is alive and connected.")
            else:
                logger.warning("💓 HEARTBEAT: Bot is DISCONNECTED!")
        except Exception as e:
            logger.error(f"💓 HEARTBEAT ERROR: {e}")
        await asyncio.sleep(300)

# ─────────────────────────────────────────────────────────────
#  Raw Update Listener (Low-level Debugging)
# ─────────────────────────────────────────────────────────────

@app.on_raw_update()
async def raw_update_handler(client: Client, update: Update, users: dict, chats: dict):
    """Logs EVERY raw update from Telegram to confirm updates are reaching the bot."""
    logger.info(f"📥 RAW UPDATE RECEIVED: {type(update).__name__}")

# ─────────────────────────────────────────────────────────────
#  Diagnostic Command
# ─────────────────────────────────────────────────────────────

@app.on_message(filters.command("test_diag") & filters.private)
async def test_diag_h(client: Client, message: Message):
    logger.info(f"🧪 DIAG COMMAND: Received /test_diag from {message.from_user.id}")
    await message.reply_text("✅ Bot is responsive to commands!")

# ─────────────────────────────────────────────────────────────
#  User Commands
# ─────────────────────────────────────────────────────────────

@app.on_message(filters.private, group=-1)
async def global_debug_logger(client: Client, message: Message):
    """Logs EVERY private message received by the bot before any other handler."""
    try:
        user = message.from_user
        uid = user.id if user else "Unknown"
        text = (message.text or message.caption or "Non-text message")[:50]
        logger.info(f"📩 MESSAGE RECEIVED from {uid}: {text}")
    except Exception as e:
        logger.error(f"DEBUG ERROR in logger: {e}")

@app.on_message(
    filters.command(["start", "help", "shop", "orders", "balance", "addbalance", "profile"])
    & filters.private
)
async def commands_h(client: Client, message: Message):
    try:
        cmd = message.command[0]
        logger.info(f"⚡ EXECUTING: /{cmd} for {message.from_user.id}")
        if   cmd == "start":      await start(client, message)
        elif cmd == "help":       await help_menu(client, message)
        elif cmd == "shop":       await shop_menu(client, message)
        elif cmd == "orders":     await orders_menu(client, message)
        elif cmd in ("balance", "profile"):
            await profile_menu(client, message)
        elif cmd == "addbalance": await deposit_menu(client, message)
        logger.info(f"✅ COMPLETED: /{cmd} for {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ FATAL CMD ERROR: {e}")
        traceback.print_exc()
        try:
            await message.reply_text(f"❌ Command Error: {e}")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
#  Admin Commands
# ─────────────────────────────────────────────────────────────

ADMIN_CMDS = [
    "stats", "addbal", "broadcast", "addadmin", "rmadmin",
    "setfsub", "setupi", "addacc", "recovery", "fa2", "sold", "login"
]

@app.on_message(
    filters.command(ADMIN_CMDS) & filters.private
)
async def admin_cmds(client: Client, message: Message):
    try:
        if not is_admin(message.from_user.id):
            logger.warning(f"🚫 NON-ADMIN {message.from_user.id} TRIED ADMIN CMD: {message.text}")
            return
        cmd = message.command[0]
        logger.info(f"👑 EXECUTING ADMIN: /{cmd} for {message.from_user.id}")
        if   cmd == "stats":                 await stats(client, message)
        elif cmd == "addbal":                await add_bal(client, message)
        elif cmd == "broadcast":             await broadcast(client, message)
        elif cmd in ("addadmin", "rmadmin"): await manage_admins(client, message)
        elif cmd in ("setfsub", "setupi", "recovery", "fa2"):
            await set_config_cmd(client, message)
        elif cmd == "addacc":                await add_acc_start(client, message)
        elif cmd == "sold":                  await sold_accounts(client, message)
        elif cmd == "login":
            from handlers.session import login_command
            await login_command(client, message)
        logger.info(f"✅ COMPLETED ADMIN: /{cmd} for {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ FATAL ADMIN CMD ERROR: {e}")
        traceback.print_exc()
        try:
            await message.reply_text(f"❌ Admin Command Error: {e}")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
#  Generic Message Handler
# ─────────────────────────────────────────────────────────────

_all_commands = [
    "start", "help", "shop", "orders", "balance", "addbalance", "profile", "test_diag"
] + ADMIN_CMDS

@app.on_message(
    filters.private
    & ~filters.command(_all_commands)
)
async def msg_h(client: Client, message: Message):
    try:
        from handlers.session import session_states, handle_session_message
        from handlers.payment import payment_admin_states, handle_admin_rejection_reason
        from handlers.admin  import admin_states, handle_admin_msg

        user_id = message.from_user.id
        logger.info(f"🛤️ ROUTING MSG: from {user_id}")

        if user_id in payment_admin_states:
            logger.info(f"🛤️ ROUTING: payment_admin_states for {user_id}")
            await handle_admin_rejection_reason(client, message)
        elif user_id in session_states:
            logger.info(f"🛤️ ROUTING: session_states for {user_id}")
            await handle_session_message(client, message)
        elif is_admin(user_id) and user_id in admin_states:
            logger.info(f"🛤️ ROUTING: admin_states for {user_id}")
            await handle_admin_msg(client, message)
        else:
            logger.info(f"🛤️ ROUTING: generic handle_message for {user_id}")
            await handle_message(client, message)
    except Exception as e:
        logger.error(f"❌ FATAL MSG ROUTING ERROR: {e}")
        traceback.print_exc()

# ─────────────────────────────────────────────────────────────
#  Callback Query Handler
# ─────────────────────────────────────────────────────────────

_FSUB_GUARDED = {"open_shop", "open_deposit", "open_orders", "open_profile"}

async def _run_fsub_check(client: Client, callback: CallbackQuery) -> bool:
    from handlers.fsub import check_fsub
    return await check_fsub(client, callback.message)

@app.on_callback_query()
async def cb_h(client: Client, callback: CallbackQuery):
    data = callback.data
    logger.info(f"🔘 CALLBACK RECEIVED: {data} from {callback.from_user.id}")

    if not (data.startswith("approve_") or data.startswith("reject_")):
        try:
            await callback.answer()
        except Exception as e:
            logger.debug(f"DEBUG: callback.answer error: {e}")

    try:
        if data == "check_fsub_again":
            logger.info(f"⚡ EXECUTING: recheck_fsub_callback for {callback.from_user.id}")
            await recheck_fsub_callback(client, callback)
            return

        if data == "cancel_deposit":
            user_states.pop(callback.from_user.id, None)
            try:
                await callback.message.delete()
            except Exception:
                pass
            await start(client, callback)
            return

        if data in _FSUB_GUARDED:
            if not await _run_fsub_check(client, callback):
                return

        logger.info(f"🛤️ ROUTING CALLBACK: {data} for {callback.from_user.id}")
        if   data == "back_to_main":    await start(client, callback)
        elif data == "open_shop":       await shop_menu(client, callback)
        elif data == "open_deposit":    await deposit_menu(client, callback)
        elif data == "open_profile":    await profile_menu(client, callback)
        elif data == "open_orders":     await orders_menu(client, callback)
        elif data == "open_help":       await help_menu(client, callback)
        elif data in ("help_user", "help_admin"):
            await help_detail(client, callback)

        elif data == "open_rules":
            from info import RULES_TEXT
            from handlers.user import safe_edit
            await safe_edit(callback, RULES_TEXT,
                InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]))

        elif data == "open_support":
            from info import SUPPORT_TEXT
            from handlers.user import safe_edit
            await safe_edit(callback, SUPPORT_TEXT,
                InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]))

        elif data.startswith("sort_opts_"):    await sort_options_menu(client, callback)
        elif data.startswith("view_country_"): await view_country_accounts(client, callback)
        elif data.startswith("buy_acc_"):      await buy_account(client, callback)
        elif data.startswith("get_otp_"):      await get_otp_logic(client, callback)
        elif data.startswith("logout_acc_"):   await logout_acc_logic(client, callback)

        elif data.startswith("approve_") or data.startswith("reject_"):
            await payment_callback(client, callback)

        elif data.startswith("setup_"):
            from handlers.session import handle_automation_callback
            await handle_automation_callback(client, callback)

        elif data == "set_upi_image":
            await set_upi_image_start(client, callback)

    except Exception as e:
        logger.error(f"❌ [CB ERROR] data={data!r} error={type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            await callback.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
        except Exception:
            pass
        try:
            await start(client, callback)
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
#  Webhook clear
# ─────────────────────────────────────────────────────────────

async def delete_webhook():
    url = f"https://api.telegram.org/bot{_clean_token}/deleteWebhook?drop_pending_updates=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("result"):
                    logger.info("✅ Webhook cleared (drop_pending_updates=true)")
                else:
                    logger.warning(f"⚠️  deleteWebhook response: {data}")
    except Exception as e:
        logger.error(f"⚠️  Could not call deleteWebhook: {e}")

# ─────────────────────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────────────────────

async def main():
    logger.info("🔄 Initializing database...")
    init_db()
    logger.info("✅ Database initialized successfully!")

    await delete_webhook()
    asyncio.create_task(heartbeat())

    async with app:
        me = await app.get_me()
        logger.info(f"🚀 Bot is running... @{me.username} (id={me.id})")
        await start_web()
        await app.invoke(pyrogram.raw.functions.updates.GetState())
        logger.info("✅ Update state synced")
        await idle()
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user.")
    except Exception as e:
        logger.error(f"💥 CRITICAL ERROR AT RUNTIME: {e}")
        traceback.print_exc()
