import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
#           FALLBACK CONFIGURATIONS
# ============================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 123456))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
LOG_GROUP = int(os.environ.get("LOG_GROUP", -100123456789))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://user:pass@cluster.mongodb.net/")

# ── UI TEXTS ─────────────────────────────────

START_MESSAGE = """
🔥 **Welcome to Hind Deals!**

👋 Hello {name}!
Use the menu below to explore features.

🛒 Ready-made Telegram accounts available.
"""

RULES_TEXT = """
📋 **Rules & Guidelines**

**1. Secure your Accounts:**
   • Change 2-step verification immediately
   • Update recovery email address
   • Change login email (if feature enabled)
   • Terminate other devices after 24 hours

**2. Prohibited Activities:**
   • No spam or mass messaging
   • No promotion or advertising
   • No illegal activities
   • No harassment or abuse

**3. Refund Policy:**
   • All deposits are non-refundable.
   • No refunds after the account is delivered under any circumstances.
   • All refund decisions are final and at the sole discretion of the Hind Deals Team.
"""

SUPPORT_TEXT = """
🛟 **SUPPORT**

For assistance, please contact our support team.

📌 Common Issues:
• Payment not credited → Share UTR + screenshot to admin
• Account not working → Contact within 10 minutes of purchase
• Other issues → Describe your problem clearly

⚠️ Response time: Within 24 hours.
"""

PROFILE_TEXT = """
👤 **USER PROFILE**

• 🧑‍💻 User: {name}
• 💰 Current Balance: ₹{balance}
• 🪙 Total Spent: ₹{total_spent}
• 🛒 Total Purchases: {total_purchases}

💡 Need more funds? Use the '💵 Deposit' button below to top up your balance.
"""

HELP_TEXT = """
📖 **HELP CENTER**

Select the category you need help with:
"""

USER_HELP = """
👤 **USER COMMANDS**

• /start - Start the bot & Main menu
• /profile - View your account details
• /shop - Buy Telegram accounts
• /orders - View your active accounts & OTPs
• /deposit - Add funds to your wallet
• /rules - Read our guidelines
• /help - Show this menu
"""

ADMIN_HELP = """
🔐 **ADMIN COMMANDS**

• /stats - Bot statistics
• /addbal <id> <amt> - Manual credit
• /broadcast <msg> - Send to all users
• /addadmin <id> - Add new admin
• /rmadmin <id> - Remove an admin
    • /setfsub <channel_id/link> - Set FSub
    • /setupi <id> <name> - Set payment UPI
    • /recovery <email> - Set recovery email
    • /fa2 <password> - Set admin 2FA password
    • /sold - View sold accounts panel
    • /addacc - Add account to shop (interactive)
    • /login - Link admin session (interactive)
    """
