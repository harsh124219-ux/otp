from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from database import get_config, is_admin


async def check_fsub(client: Client, message: Message) -> bool:
    """
    Returns True if the user is allowed to proceed.
    - Always True for admins.
    - Always True if no FSub channel is configured.
    - Prompts user to join and returns False if they haven't joined.

    NOTE: `message` must be a real pyrogram Message object (not CallbackQuery).
          For callbacks, pass `callback.message`.
    """
    if is_admin(message.from_user.id):
        return True

    config = get_config()
    fsub = config.get("fsub_channel")

    if not fsub:
        return True

    try:
        await client.get_chat_member(fsub, message.from_user.id)
        return True
    except UserNotParticipant:
        try:
            chat = await client.get_chat(fsub)
            link = chat.invite_link or f"https://t.me/{chat.username}"
        except Exception:
            link = f"https://t.me/{str(fsub).replace('@', '')}"

        # FIX: callback_data now points to "check_fsub_again" not "back_to_main"
        # so clicking "I Have Joined" will RE-CHECK membership before showing the menu.
        await message.reply_text(
            "⚠️ **ACCESS DENIED**\n\n"
            "You must join our channel to use this bot.\n"
            "After joining, tap the button below.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=link)],
                [InlineKeyboardButton("✅ I Have Joined — Check Again", callback_data="check_fsub_again")]
            ])
        )
        return False
    except Exception as e:
        # Any other API error → don't block the user
        print(f"FSub check error (non-blocking): {e}")
        return True


async def recheck_fsub_callback(client: Client, callback):
    """
    Called when user taps '✅ I Have Joined — Check Again'.
    Re-checks membership; if passed, sends them to main menu.
    """
    from pyrogram.types import CallbackQuery
    config = get_config()
    fsub = config.get("fsub_channel")

    if not fsub:
        # No fsub — just go to main menu
        from handlers.user import start
        await start(client, callback)
        return

    user_id = callback.from_user.id
    joined = False
    try:
        member = await client.get_chat_member(fsub, user_id)
        # member.status could be banned/left — check it properly
        from pyrogram.enums import ChatMemberStatus
        if member.status not in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT):
            joined = True
    except UserNotParticipant:
        joined = False
    except Exception:
        joined = True  # non-blocking on other errors

    if joined:
        await callback.answer("✅ Verified! Welcome.", show_alert=False)
        from handlers.user import start
        await start(client, callback)
    else:
        try:
            chat = await client.get_chat(fsub)
            link = chat.invite_link or f"https://t.me/{chat.username}"
        except Exception:
            link = f"https://t.me/{str(fsub).replace('@', '')}"

        await callback.answer("❌ You haven't joined yet!", show_alert=True)
        await callback.message.edit_text(
            "⚠️ **ACCESS DENIED**\n\n"
            "You must join our channel to use this bot.\n"
            "After joining, tap the button below.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=link)],
                [InlineKeyboardButton("✅ I Have Joined — Check Again", callback_data="check_fsub_again")]
            ])
        )
