from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    is_admin, add_admin, remove_admin, update_config, 
    users_col, transactions_col, add_balance, add_account
)
from info import API_ID, API_HASH
import asyncio

# Admin state for interactive account adding
admin_states = {}

async def stats(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    
    total_users = users_col.count_documents({})
    total_txns = transactions_col.count_documents({})
    pending = transactions_col.count_documents({"status": "pending"})
    
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📋 Total Transactions: {total_txns}\n"
        f"⏳ Pending: {pending}"
    )

async def add_bal(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    try:
        _, user_id, amount = message.text.split()
        add_balance(int(user_id), float(amount))
        await message.reply_text(f"✅ Added ₹{amount} to user `{user_id}`")
    except:
        await message.reply_text("Usage: /addbal <user_id> <amount>")

async def broadcast(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    text = message.text.split(None, 1)
    if len(text) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return
    
    sent = 0
    async for user in users_col.find({}):
        try:
            await client.send_message(user["user_id"], text[1])
            sent += 1
            await asyncio.sleep(0.1) # Avoid flood
        except: pass
    await message.reply_text(f"✅ Broadcast sent to {sent} users.")

async def manage_admins(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    cmd = message.command[0]
    try:
        target_id = int(message.command[1])
        if cmd == "addadmin":
            add_admin(target_id)
            await message.reply_text(f"✅ User `{target_id}` added as admin.")
        elif cmd == "rmadmin":
            if remove_admin(target_id):
                await message.reply_text(f"✅ User `{target_id}` removed from admins.")
            else:
                await message.reply_text("❌ Cannot remove primary admin.")
    except:
        await message.reply_text(f"Usage: /{cmd} <user_id>")

async def set_config_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    cmd = message.command[0]
    try:
        if cmd == "setfsub":
            val = message.command[1]
            update_config("fsub_channel", val)
            await message.reply_text(f"✅ FSub set to: {val}")
        elif cmd == "setupi":
            upi_id = message.command[1]
            upi_name = " ".join(message.command[2:])
            update_config("upi_id", upi_id)
            update_config("upi_name", upi_name)
            await message.reply_text(f"✅ UPI updated: {upi_id} ({upi_name})")
    except:
        await message.reply_text(f"Usage:\n/setfsub <id/link>\n/setupi <id> <name>")

async def add_acc_start(client: Client, message: Message):
    if not is_admin(message.from_user.id): return
    await message.reply_text("📱 Enter the **phone number** for the new account:")
    admin_states[message.from_user.id] = {"step": "phone"}

async def handle_admin_msg(client: Client, message: Message):
    admin_id = message.from_user.id
    state = admin_states.get(admin_id)
    if not state: return

    step = state["step"]
    if step == "phone":
        admin_states[admin_id] = {"step": "session", "phone": message.text.strip()}
        await message.reply_text("🔑 Now enter the **session string**:")
    elif step == "session":
        admin_states[admin_id].update({"step": "country", "session": message.text.strip()})
        await message.reply_text("🌍 Enter the **country name** (e.g., India):")
    elif step == "country":
        admin_states[admin_id].update({"step": "price", "country": message.text.strip()})
        await message.reply_text("💰 Enter the **price** for this account:")
    elif step == "price":
        try:
            price = float(message.text.strip())
            phone = state["phone"]
            session = state["session"]
            country = state["country"]
            add_account(phone, session, country, price)
            await message.reply_text(f"✅ Account `{phone}` added to {country} for ₹{price}!")
            admin_states.pop(admin_id, None)
        except:
            await message.reply_text("❌ Invalid price. Enter a number:")
