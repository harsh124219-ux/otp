from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from database import get_config, is_admin

async def check_fsub(client: Client, message: Message):
    if is_admin(message.from_user.id):
        return True

    config = get_config()
    fsub = config.get("fsub_channel")
    
    if not fsub:
        return True

    try:
        # Check if user is in channel
        await client.get_chat_member(fsub, message.from_user.id)
        return True
    except UserNotParticipant:
        # Get channel link for button
        try:
            chat = await client.get_chat(fsub)
            link = chat.invite_link or f"https://t.me/{chat.username}"
        except:
            link = f"https://t.me/{fsub.replace('@', '')}"

        await message.reply_text(
            "⚠️ **ACCESS DENIED**\n\nYou must join our channel to use this bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=link)],
                [InlineKeyboardButton("🔄 I Have Joined", callback_data="back_to_main")]
            ])
        )
        return False
    except Exception as e:
        print(f"FSub Error: {e}")
        return True # Don't block if there's an API error
