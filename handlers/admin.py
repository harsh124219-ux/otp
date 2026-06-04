from pyrogram import Client, filters
from pyrogram.types import Message
from database import (
    get_transaction, update_transaction_status,
    add_balance, users_col, transactions_col
)
from info import ADMIN_ID


async def stats(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    total_users = users_col.count_documents({})
    total_txns = transactions_col.count_documents({})
    pending = transactions_col.count_documents({"status": "pending"})
    approved = transactions_col.count_documents({"status": "approved"})

    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📋 Total Transactions: {total_txns}\n"
        f"⏳ Pending: {pending}\n"
        f"✅ Approved: {approved}"
    )


async def add_bal(client: Client, message: Message):
    """Manual balance add: /addbal <user_id> <amount>"""
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id, amount = message.text.split()
        add_balance(int(user_id), float(amount))
        await message.reply_text(f"✅ Added ₹{amount} to user `{user_id}`")
    except Exception:
        await message.reply_text("Usage: /addbal <user_id> <amount>")


async def broadcast(client: Client, message: Message):
    """Broadcast: /broadcast <message>"""
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.split(None, 1)
    if len(text) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return

    msg = text[1]
    users = users_col.find({})
    sent = 0
    for user in users:
        try:
            await client.send_message(user["user_id"], msg)
            sent += 1
        except Exception:
            pass
    await message.reply_text(f"✅ Broadcast sent to {sent} users.")
