"""
main.py — OTP Ocean Bot
────────────────────────
Entry point. Registers all handlers and starts the bot.
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from info import BOT_TOKEN, API_ID, API_HASH
from database import is_admin

from handlers.user import (
    start, profile_menu, orders_menu,
    deposit_menu, help_menu, help_detail,
    handle_message, user_states
)
from handlers.shop import (
    shop_menu, sort_options_menu, view_country_accounts,
    buy_account, get_otp_logic, logout_acc_logic
)
from handlers.admin import (
    stats, add_bal, broadcast, manage_admins,
    set_config_cmd, add_acc_start, sold_accounts,
    set_upi_image_start
)
from handlers.payment import payment_callback
from handlers.fsub import recheck_fsub_callback

app = Client(
    "otpbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# ─────────────────────────────────────────────────────────────
#  User Commands
# ─────────────────────────────────────────────────────────────

@app.on_message(
    filters.command(["start", "help", "shop", "orders", "balance", "addbalance", "profile"])
    & filters.private
)
async def commands_h(client: Client, message: Message):
    cmd = message.command[0]
    if   cmd == "start":       await start(client, message)
    elif cmd == "help":        await help_menu(client, message)
    elif cmd == "shop":        await shop_menu(client, message)
    elif cmd == "orders":      await orders_menu(client, message)
    elif cmd in ("balance", "profile"):
        await profile_menu(client, message)
    elif cmd == "addbalance":  await deposit_menu(client, message)


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
    if   cmd == "stats":                await stats(client, message)
    elif cmd == "addbal":               await add_bal(client, message)
    elif cmd == "broadcast":            await broadcast(client, message)
    elif cmd in ("addadmin", "rmadmin"):await manage_admins(client, message)
    elif cmd in ("setfsub", "setupi", "recovery", "fa2"):
        await set_config_cmd(client, message)
    elif cmd == "addacc":               await add_acc_start(client, message)
    elif cmd == "sold":                 await sold_accounts(client, message)
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

    # Priority order: payment rejection → session login → admin interactive → user deposit
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

# Callbacks that require fsub check before proceeding
_FSUB_GUARDED = {"open_shop", "open_deposit", "open_orders", "open_profile"}


async def _run_fsub_check(client: Client, callback: CallbackQuery) -> bool:
    """
    Returns True if the user passed fsub or is admin.
    Handles the reply/edit internally on failure.
    """
    from handlers.fsub import check_fsub
    return await check_fsub(client, callback.message)


@app.on_callback_query()
async def cb_h(client: Client, callback: CallbackQuery):
    data = callback.data
    await callback.answer()   # acknowledge immediately to stop the spinner

    try:
        # ── FSub re-check callback ─────────────────────────────
        if data == "check_fsub_again":
            await recheck_fsub_callback(client, callback)
            return

        # ── Cancel deposit ─────────────────────────────────────
        if data == "cancel_deposit":
            user_states.pop(callback.from_user.id, None)
            try:
                await callback.message.delete()
            except Exception:
                pass
            await start(client, callback)
            return

        # ── FSub guard for key menus ───────────────────────────
        if data in _FSUB_GUARDED:
            if not await _run_fsub_check(client, callback):
                return  # check_fsub already replied with the join prompt

        # ── Main navigation ────────────────────────────────────
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

        elif data in ("help_user", "help_admin"):
            await help_detail(client, callback)

        elif data == "open_rules":
            from info import RULES_TEXT
            from handlers.user import safe_edit
            await safe_edit(
                callback, RULES_TEXT,
                InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            )

        elif data == "open_support":
            from info import SUPPORT_TEXT
            from handlers.user import safe_edit
            await safe_edit(
                callback, SUPPORT_TEXT,
                InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            )

        # ── Shop flow ──────────────────────────────────────────
        elif data.startswith("sort_opts_"):
            await sort_options_menu(client, callback)

        elif data.startswith("view_country_"):
            await view_country_accounts(client, callback)

        elif data.startswith("buy_acc_"):
            await buy_account(client, callback)

        elif data.startswith("get_otp_"):
            await get_otp_logic(client, callback)

        elif data.startswith("logout_acc_"):
            await logout_acc_logic(client, callback)

        # ── Payment approval ───────────────────────────────────
        elif data.startswith("approve_") or data.startswith("reject_"):
            await payment_callback(client, callback)

        # ── Session automation ─────────────────────────────────
        elif data.startswith("setup_"):
            from handlers.session import handle_automation_callback
            await handle_automation_callback(client, callback)

        # ── Admin: UPI image update ────────────────────────────
        elif data == "set_upi_image":
            await set_upi_image_start(client, callback)

    except Exception as e:
        print(f"[CB ERROR] data={data!r}  error={e}")
        # Soft fallback — go back to main menu without crashing
        try:
            await start(client, callback)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────────────────────

async def main():
    async with app:
        print("✅ Bot is running...")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
