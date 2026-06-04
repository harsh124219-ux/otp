from pyrogram import Client
from pyrogram.types import CallbackQuery, Message
from database import (
    update_transaction_status, add_balance,
    get_transaction, is_admin
)
from info import LOG_GROUP

# State tracker for capturing dynamic rejection reasons
payment_admin_states = {}

async def payment_callback(client: Client, callback: CallbackQuery):
    await callback.answer()

    if not is_admin(callback.from_user.id):
        await callback.answer("❌ You are not authorized!", show_alert=True)
        return

    data = callback.data

    # ── APPROVE TRANSACTION ─────────────────────────────
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
        except Exception:
            pass

    # ── REJECT TRANSACTION ──────────────────────────────
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

        # Save context state and ask admin for a reason
        payment_admin_states[callback.from_user.id] = {
            "utr": utr,
            "user_id": user_id,
            "log_message": callback.message
        }
        
        await client.send_message(
            chat_id=callback.from_user.id,
            text=f"💬 Please reply to this message with the **reason** for rejecting UTR `{utr}`:"
        )

# Call this from your main.py message handler if payment_admin_states contains the user's ID
async def handle_admin_rejection_reason(client: Client, message: Message):
    admin_id = message.from_user.id
    state = payment_admin_states.get(admin_id)
    
    if not state:
        return

    reason = message.text.strip()
    utr = state["utr"]
    user_id = state["user_id"]
    log_message = state["log_message"]

    update_transaction_status(utr, "rejected")

    try:
        # Edit layout inside the log group
        await log_message.edit_caption(
            (log_message.caption or "") + f"\n\n❌ **REJECTED BY ADMIN**\n📝 **Reason:** {reason}"
        )
    except Exception:
        pass

    try:
        # Pass identical reason data to the user
        await client.send_message(
            user_id,
            f"❌ **Payment Rejected**\n\n"
            f"Your payment with UTR `{utr}` was rejected by the administrator.\n\n"
            f"⚠️ **Reason:** {reason}\n\n"
            f"Please review your transaction details or try again with proper proof."
        )
        await message.reply_text("✅ Rejection reason sent to the user.")
    except Exception as e:
        await message.reply_text(f"⚠️ Saved, but couldn't message user directly: {e}")

    payment_admin_states.pop(admin_id, None)
