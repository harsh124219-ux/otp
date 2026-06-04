import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
#           FILL ALL DETAILS IN .env
# ============================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 123456))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
LOG_GROUP = int(os.environ.get("LOG_GROUP", -100123456789))
UPI_ID = os.environ.get("UPI_ID", "yourname@upi")
UPI_NAME = os.environ.get("UPI_NAME", "Your Name")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://user:pass@cluster.mongodb.net/")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBotUsername")
SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "@helpdesk_nrbot")

# Pricing per country (Example)
COUNTRY_PRICES = {
    "🇮🇳 India": 15.0,
    "🇺🇸 USA": 20.0,
    "🇷🇺 Russia": 12.0,
    "🇬🇧 UK": 25.0
}

# UI TEXTS
START_MESSAGE = """
🔥 Welcome to Hind Deals!

👋 Hello {name}!
Use the menu below to explore features.

🛒 Ready-made Telegram accounts available.
"""

RULES_TEXT = """
📋 Rules & Guidelines

1. Secure your Accounts:
   • Change 2-step verification immediately
   • Update recovery email address
   • Change login email (if feature enabled)
   • Terminate other devices after 24 hours

2. Prohibited Activities:
   • No spam or mass messaging
   • No promotion or advertising
   • No illegal activities
   • No harassment or abuse

3. Refund Policy:
   • All deposits are non-refundable.
   • No refunds after the account is delivered under any circumstances.
   • All refund decisions are final and at the sole discretion of the Hind Deals Team.
"""

SUPPORT_TEXT = f"""
🛟 SUPPORT CENTER

Facing any issue?  
Contact our support team here 👉 {SUPPORT_CHAT}

⚠️ Important Guidelines:
• Avoid spamming the chat  
• Explain your issue clearly  
• Attach a proper screenshot  

📌 Following these steps ensures a faster response.
"""

PROFILE_TEXT = """
👤 **USER PROFILE**

• 🧑‍💻 User: {name}
• 💰 Current Balance: ₹{balance}
• 🪙 Total Spent: ₹{total_spent}
• 🛒 Total Purchases: {total_purchases}

💡 Need more funds? Use the '💵 Deposit' button below to top up your balance.
"""
