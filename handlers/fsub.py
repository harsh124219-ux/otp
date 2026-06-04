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
    """
    # Admins bypass FSub
    if is_admin(message.from_user.id):
        return True

    config = get_config()
    fsub = config.get("fsub_channel")

    # No FSub configured → let everyone through automatically
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

        await message.reply_text(
            "⚠️ **ACCESS DENIED**\n\nYou must join our channel to use this bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=link)],
                [InlineKeyboardButton("🔄 I Have Joined", callback_data="back_to_main")]
            ])
        )
        return False
    except Exception as e:
        # Any other API error → don't block the user
        print(f"FSub check error (non-blocking): {e}")
        return True
