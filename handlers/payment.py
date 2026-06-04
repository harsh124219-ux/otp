from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    update_transaction_status, add_balance,
    get_transaction
)
from info import ADMIN_ID


async def payment_callback(client: Client, callback: CallbackQuery):
    await callback.answer()

    # Only admin can approve/reject
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ You are not authorized!", show_alert=True)
        return

    data = callback.data

    # ── APPROVE ─────────────────────────────
    if data.startswith("approve_"):
        parts = data.split("_")
        # approve_<utr>_<user_id>_<amount>
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

        # Credit balance
        add_balance(user_id, amount)
        update_transaction_status(utr, "approved")

        # Edit log message
        await callback.message.edit_caption(
            callback.message.caption + "\n\n✅ **APPROVED**"
        )

        # Notify user
        await client.send_message(
            user_id,
            f"✅ **Payment Approved!**\n\n"
            f"💰 ₹{amount} has been added to your balance.\n"
            f"🔖 UTR: `{utr}`\n\n"
            f"Use /balance to check your balance."
        )

    # ── REJECT ──────────────────────────────
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

        update_transaction_status(utr, "rejected")

        # Edit log message
        await callback.message.edit_caption(
            callback.message.caption + "\n\n❌ **REJECTED**"
        )

        # Notify user
        await client.send_message(
            user_id,
            f"❌ **Payment Rejected**\n\n"
            f"Your payment with UTR `{utr}` was not verified.\n\n"
            f"🔁 Please recheck:\n"
            f"• Screenshot is clear and valid\n"
            f"• UTR number is correct\n"
            f"• Payment was sent to the correct UPI ID\n\n"
            f"If payment was deducted from your account, "
            f"please contact the owner with your bank receipt."
        )
