from pyrogram import Client
from pyrogram.types import CallbackQuery
from database import get_balance, deduct_balance, add_balance


async def buy_otp_handler(client: Client, callback: CallbackQuery):
    """
    Legacy OTP handler (single session model).
    Main flow now uses the shop/order system in handlers/shop.py.
    """
    from database import get_config
    config = get_config()
    otp_price = config.get("otp_price", 10.0)
    user_id = callback.from_user.id
    balance = get_balance(user_id)

    if balance < otp_price:
        await callback.answer(f"❌ Insufficient balance! Price: ₹{otp_price}", show_alert=True)
        return

    await callback.message.edit_text("⏳ Processing your OTP request...")

    if not deduct_balance(user_id, otp_price):
        await callback.message.edit_text("❌ Failed to deduct balance. Please try again.")
        return

    # Refund — direct OTP service inactive, use shop instead
    add_balance(user_id, otp_price)
    await callback.message.edit_text(
        "⚠️ **Direct OTP service is not active.**\n\n"
        "Please use the 🛒 Shop to purchase a Telegram account and fetch OTPs from there."
    )
