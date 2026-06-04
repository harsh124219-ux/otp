from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import (
    is_admin, add_admin, remove_admin, update_config,
    users_col, transactions_col, add_balance, add_account, get_config
)
from info import API_ID, API_HASH
import asyncio

# Admin state for interactive flows
admin_states = {}


async def stats(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return

    total_users = users_col.count_documents({})
    total_txns = transactions_col.count_documents({})
    pending = transactions_col.count_documents({"status": "pending"})

    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"📋 Total Transactions: `{total_txns}`\n"
        f"⏳ Pending Approvals: `{pending}`"
    )


async def add_bal(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, user_id, amount = message.text.split()
        add_balance(int(user_id), float(amount))
        await message.reply_text(f"✅ Added ₹{amount} to user `{user_id}`")
    except Exception:
        await message.reply_text("Usage: /addbal <user_id> <amount>")


async def broadcast(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.split(None, 1)
    if len(text) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return

    # pymongo .find() is synchronous — run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    users = await loop.run_in_executor(None, lambda: list(users_col.find({}, {"user_id": 1})))

    sent = 0
    failed = 0
    for user in users:
        try:
            await client.send_message(user["user_id"], text[1])
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await message.reply_text(f"✅ Broadcast done!\n📤 Sent: {sent}\n❌ Failed: {failed}")


async def manage_admins(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
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
                await message.reply_text("❌ Cannot remove the primary admin.")
    except Exception:
        await message.reply_text(f"Usage: /{cmd} <user_id>")


async def set_config_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    cmd = message.command[0]
    try:
        if cmd == "setfsub":
            val = message.command[1]
            update_config("fsub_channel", val)
            await message.reply_text(f"✅ FSub channel set to: `{val}`")
        elif cmd == "setupi":
            upi_id = message.command[1]
            upi_name = " ".join(message.command[2:]) if len(message.command) > 2 else "Not Set"
            update_config("upi_id", upi_id)
            update_config("upi_name", upi_name)
            config = get_config()
            upi_img = config.get("upi_image_file_id")

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼️ Update UPI Image/QR", callback_data="set_upi_image")],
                [InlineKeyboardButton("✅ Done", callback_data="back_to_main")]
            ])
            text = f"✅ UPI updated!\n\n🏦 UPI ID: `{upi_id}`\n👤 Name: {upi_name}"
            if upi_img:
                text += "\n🖼️ QR Image: Already set (tap button to update)"
            else:
                text += "\n🖼️ QR Image: Not set yet"
            await message.reply_text(text, reply_markup=markup)
    except Exception:
        await message.reply_text("Usage:\n/setfsub <id/link>\n/setupi <upi_id> <name>")


# ── UPI Image Handler ────────────────────────

async def set_upi_image_start(client: Client, callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🖼️ **SET UPI QR IMAGE**\n\nSend the UPI QR code or payment image now.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="back_to_main")]])
    )
    admin_states[callback.from_user.id] = {"step": "waiting_upi_image"}


# ── Interactive Add Account ──────────────────

async def add_acc_start(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.reply_text(
        "📱 Enter the **phone number** for the new account:\n\n_(e.g. +919876543210)_"
    )
    admin_states[message.from_user.id] = {"step": "phone"}


async def handle_admin_msg(client: Client, message: Message):
    admin_id = message.from_user.id
    state = admin_states.get(admin_id)
    if not state:
        return

    step = state["step"]

    # ── UPI Image upload step ──────────────────
    if step == "waiting_upi_image":
        if not message.photo:
            await message.reply_text("📸 Please send a **photo** (QR code / UPI image).")
            return
        file_id = message.photo.file_id
        update_config("upi_image_file_id", file_id)
        admin_states.pop(admin_id, None)
        await message.reply_text(
            "✅ UPI image saved successfully!\n\nUsers will now see this when they deposit.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
        )
        return

    # ── Add Account steps ──────────────────────
    if step == "phone":
        admin_states[admin_id] = {"step": "session", "phone": message.text.strip()}
        await message.reply_text("🔑 Now enter the **session string**:")

    elif step == "session":
        admin_states[admin_id].update({"step": "country", "session": message.text.strip()})
        await message.reply_text("🌍 Enter the **country name** (e.g., India):")

    elif step == "country":
        admin_states[admin_id].update({"step": "price", "country": message.text.strip()})
        await message.reply_text("💰 Enter the **price** for this account (e.g., 150):")

    elif step == "price":
        try:
            price = float(message.text.strip())
            phone = state["phone"]
            session = state["session"]
            country = state["country"]
            add_account(phone, session, country, price)
            await message.reply_text(
                f"✅ Account `{phone}` added!\n🌍 Country: {country}\n💰 Price: ₹{price}"
            )
            admin_states.pop(admin_id, None)
        except ValueError:
            await message.reply_text("❌ Invalid price. Please enter a number (e.g., 150):")
