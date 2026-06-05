import asyncio
import sys
import pyrogram
import aiohttp
from pyrogram import Client, filters, raw
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from info import BOT_TOKEN, API_ID, API_HASH
from database import is_admin

# ── Handler imports with startup diagnostics ─────────────────
try:
    from handlers.user import (
        start, profile_menu, orders_menu,
        deposit_menu, help_menu, help_detail,
        handle_message, user_states
    )
    print("✅ handlers.user loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.user failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

try:
    from handlers.shop import (
        shop_menu, sort_options_menu, view_country_accounts,
        buy_account, get_otp_logic, logout_acc_logic
    )
    print("✅ handlers.shop loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.shop failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

try:
    from handlers.admin import (
        stats, add_bal, broadcast, manage_admins,
        set_config_cmd, add_acc_start, sold_accounts,
        set_upi_image_start
    )
    print("✅ handlers.admin loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.admin failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

try:
    from handlers.payment import payment_callback
    print("✅ handlers.payment loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.payment failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

try:
    from handlers.fsub import recheck_fsub_callback
    print("✅ handlers.fsub loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.fsub failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

try:
    import handlers.session as _session_check  # noqa: F401
    print("✅ handlers.session loaded")
except Exception as _e:
    print(f"❌ FATAL: handlers.session failed to load: {_e}", file=sys.stderr)
    sys.exit(1)

_clean_token = BOT_TOKEN.strip()

app = Client(
    "otpbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=_clean_token,
    in_memory=True,      # prevents stale .session file on Heroku ephemeral disk
)


# ─────────────────────────────────────────────────────────────
#  RAW UPDATE LOGGER — prints every single update to Heroku logs
#  This tells us definitively whether Telegram is delivering updates.
#  Remove this block once the bot is confirmed working.
# ─────────────────────────────────────────────────────────────

@app.on_raw_update()
async def raw_logger(client, update, users, chats):
    print(f"[RAW UPDATE] type={type(update).__name__}")


# ─────────────────────────────────────────────────────────────
#  User Commands
# ─────────────────────────────────────────────────────────────

@app.on_message(
    filters.command(["start", "help", "shop", "orders", "balance", "addbalance", "profile"])
    & filters.private
)
async def commands_h(client: Client, message: Message):
    print(f"[CMD] /{message.command[0]} from {message.from_user.id}")
    cmd = message.command[0]
    if   cmd == "start":      await start(client, message)
    elif cmd == "help":       await help_menu(client, message)
    elif cmd == "shop":       await shop_menu(client, message)
    elif cmd == "orders":     await orders_menu(client, message)
    elif cmd in ("balance", "profile"):
        await profile_menu(client, message)
    elif cmd == "addbalance": await deposit_menu(client, message)


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
    if not is_admin(message.from_user.id):
        return
    cmd = message.command[0]
    print(f"[ADMIN CMD] /{cmd} from {message.from_user.id}")
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


# ─────────────────────────────────────────────────────────────
#  Generic Message Handler
# ─────────────────────────────────────────────────────────────

_all_commands = [
    "start", "help", "shop", "orders", "balance", "addbalance", "profile"
] + ADMIN_CMDS

@app.on_message(
    filters.private
    & ~filters.command(_all_commands)
)
async def msg_h(client: Client, message: Message):
    from handlers.session import session_states, handle_session_message
    from handlers.payment import payment_admin_states, handle_admin_rejection_reason
    from handlers.admin  import admin_states, handle_admin_msg

    user_id = message.from_user.id
    print(f"[MSG] from {user_id}: {(message.text or '')[:40]}")

    if user_id in payment_admin_states:
        await handle_admin_rejection_reason(client, message)
    elif user_id in session_states:
        await handle_session_message(client, message)
    elif is_admin(user_id) and user_id in admin_states:
        await handle_admin_msg(client, message)
    else:
        await handle_message(client, message)


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
    print(f"[CB] {data} from {callback.from_user.id}")

    if not (data.startswith("approve_") or data.startswith("reject_")):
        await callback.answer()

    try:
        if data == "check_fsub_again":
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
        print(f"[CB ERROR] data={data!r} error={type(e).__name__}: {e}")
        try:
            await callback.answer("❌ Something went wrong.", show_alert=True)
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
                    print("✅ Webhook cleared (drop_pending_updates=true)")
                else:
                    print(f"⚠️  deleteWebhook response: {data}")
    except Exception as e:
        print(f"⚠️  Could not call deleteWebhook: {e}")


# ─────────────────────────────────────────────────────────────
#  Run — using pyrogram.idle() so Pyrogram's dispatcher gets
#  full control of the event loop and can process updates.
#
#  The old asyncio.Event().wait() was blocking the loop in a way
#  that starved Pyrogram's internal polling tasks — updates
#  arrived at the socket but were never picked up (silent crash).
# ─────────────────────────────────────────────────────────────

async def main():
    await delete_webhook()
    await app.start()
    me = await app.get_me()
    print(f"✅ Bot is running... @{me.username} (id={me.id})")
    await pyrogram.idle()   # ← hands control to Pyrogram's dispatcher


if __name__ == "__main__":
    asyncio.run(main())
