from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    update_transaction_status, add_balance,
    get_transaction, is_admin
)


async def payment_callback(client: Client, callback: CallbackQuery):
    await callback.answer()

    # All admins (not just primary) can approve/reject
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ You are not authorized!", show_alert=True)
        return

    data = callback.data

    # ── APPROVE ─────────────────────────────
    if data.startswith("approve_"):
        parts = data.split("_")
        # Format: approve_<utr>_<user_id>_<amount>
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
                (callback.message.caption or "") + "\n\n✅ **APPROVED**"
            )
        except Exception:
            pass

        try:
            await client.send_message(
                user_id,
                f"✅ **Payment Approved!**\n\n"
                f"💰 ₹{amount} has been credited to your balance.\n"
                f"🔖 UTR: `{utr}`\n\n"
                f"Use /start to continue shopping."
            )
        except Exception as e:
            print(f"Failed to notify user {user_id}: {e}")

    # ── REJECT ──────────────────────────────
    elif data.startswith("reject_"):
        parts = data.split("_")
        # Format: reject_<utr>_<user_id>
        utr = parts[1]
        user_id = int(parts[2])

        txn = get_transaction(utr)
        if not txn:
            await callback.answer("Transaction not found!", show_alert=True)
            return
        if txn["status"] == "rejected":
            await callback.answer("Already rejected!", show_alert=True)
            return

        update_transaction_status(utr, "rejected")

        try:
            await callback.message.edit_caption(
                (callback.message.caption or "") + "\n\n❌ **REJECTED**"
            )
        except Exception:
            pass

        try:
            await client.send_message(
                user_id,
                f"❌ **Payment Rejected**\n\n"
                f"Your payment with UTR `{utr}` was not verified.\n\n"
                f"🔁 Please check:\n"
                f"• Screenshot is clear and readable\n"
                f"• UTR number is correct\n"
                f"• Payment was sent to the correct UPI ID\n\n"
                f"If money was deducted from your account, "
                f"contact admin with your bank receipt."
            )
        except Exception as e:
            print(f"Failed to notify user {user_id}: {e}")
