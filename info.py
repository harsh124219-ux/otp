import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
#           FALLBACK CONFIGURATIONS
# ============================================
HEROKU_APP_NAME = otpbot
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 123456))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
LOG_GROUP = int(os.environ.get("LOG_GROUP", -100123456789))
MONGO_URL = os.environ.get("MONGO_URL", "")

# ── UI TEXTS ─────────────────────────────────

START_MESSAGE = """
🔥 **Welcome to OTP Ocean!**

👋 Hello {name}!
Use the menu below to explore features.

🛒 Ready-made Telegram accounts available.
"""

# FIX BUG 4: RULES_TEXT was defined TWICE — second one overwrote first.
# Kept the more complete version here, removed the duplicate.
RULES_TEXT = """
📋 **Rules & Guidelines**

**1. Secure your Accounts:**
   • Change 2-step verification immediately
   • Update recovery email address
   • Terminate other devices after 24 hours

**2. Prohibited Activities:**
   • No spam or mass messaging
   • No promotion or advertising
   • No illegal activities
   • No harassment or abuse

**3. Refund Policy:**
   • All sales are final. Please check balance before buying.
   • No refunds after account is delivered under any circumstances.
   • All decisions are final and at the sole discretion of the team.

**4. Support:** Contact @OTPOceanSupportBot for issues.
"""

SUPPORT_TEXT = """
🛟 **SUPPORT**

For assistance, please contact our support team: @OTPOceanSupportBot

📌 Common Issues:
• Payment not credited → Share UTR + screenshot to admin
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
• /shop - Buy Telegram accounts
• /orders - View your orders
• /balance - Check your balance
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
