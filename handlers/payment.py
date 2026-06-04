from pyrogram import Client
from pyrogram.types import CallbackQuery, Message
from database import (
    update_transaction_status, add_balance,
    get_transaction, is_admin
)
from info import LOG_GROUP
from handlers.admin import admin_states # Reusing state tracker for uniformity

async def payment_callback(client: Client, callback: CallbackQuery):
    await callback.answer()

    if not is_admin(callback.from_user.id):
        await callback.answer("❌ You are not authorized!", show_alert=True)
        return

    data = callback.data

    # ── APPROVE ─────────────────────────────
    if data.startswith("approve_"):
        parts = data.split("_")
        utr = parts[1]
        user_id = int(parts[2])
        amount = float(parts[3])

        txn = get_transaction(utr)
        if not txn:
            await callback.answer("Transaction not found!", show_alert=True)
            return
        if txn["status"] == "approved":
            await callback.answer("Already approved!", show_alert=True)
            return

        add_balance(user_id, amount)
        update_transaction_status(utr, "approved")

        try:
            # Edit original message in Log Group
            await callback.message.edit_caption(
                (callback.message.caption or "") + "\n\n✅ **APPROVED BY ADMIN**"
            )
        except Exception:
            pass

        try:
            await client.send_message(
                user_id,
                f"✅ **Payment Approved!**\n\n"
                f"An amount of ₹{amount} has been added to your wallet balance."
            )
        except Exception as e:
            print(f"Failed to notify user {user_id}: {e}")

    # ── REJECT (START PROCESS) ──────────────────────────────
    elif data.startswith("reject_"):
        parts = data.split("_")
        utr = parts[1]
        user_id = int(parts[2])

        txn = get_transaction(utr)
        if not txn:
            await callback.answer("Transaction not found!", show_alert=True)
            return
        if txn["status"] == "rejected":
            await callback.answer("Already rejected!", show_alert=True)
            return

        # Prompt the admin to provide a reason for rejection
        admin_states[callback.from_user.id] = {
            "step": "waiting_rejection_reason",
            "utr": utr,
            "user_id": user_id,
            "log_message": callback.message
        }
        
        await client.send_message(
            chat_id=callback.from_user.id,
            text=f"💬 Please reply with the **reason** for rejecting UTR `{utr}`:"
        )

# Call this from your message dispatcher inside main.py if an admin message is captured under state "waiting_rejection_reason"
async def handle_rejection_reason_input(client: Client, message: Message):
    admin_id = message.from_user.id
    state = admin_states.get(admin_id)
    
    if not state or state.get("step") != "waiting_rejection_reason":
        return

    reason = message.text.strip()
    utr = state["utr"]
    user_id = state["user_id"]
    log_message = state["log_message"]

    update_transaction_status(utr, "rejected")

    try:
        # Update logs status in the Log Group
        await log_message.edit_caption(
            (log_message.caption or "") + f"\n\n❌ **REJECTED BY ADMIN**\n📝 **Reason:** {reason}"
        )
    except Exception:
        pass

    try:
        # Pass the exact reason down to the customer
        await client.send_message(
            user_id,
            f"❌ **Payment Rejected**\n\n"
            f"Your payment validation request for UTR `{utr}` was rejected by the manager.\n\n"
            f"📝 **Reason Given:** {reason}\n\n"
            f"Please double-check your inputs or contact help support."
        )
        await message.reply_text("✅ Rejection reason recorded and user notified.")
    except Exception as e:
        await message.reply_text(f"⚠️ Saved, but couldn't message user: {e}")

    admin_states.pop(admin_id, None)
