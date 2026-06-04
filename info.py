import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
#           FILL ALL DETAILS IN .env
# ============================================

# Telegram Bot Token from @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

# Get from my.telegram.org
API_ID = int(os.environ.get("API_ID", 123456))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")

# Your Telegram User ID (admin)
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))

# Log group/channel ID (where payment requests go)
LOG_GROUP = int(os.environ.get("LOG_GROUP", -100123456789))

# Your UPI ID for payments
UPI_ID = os.environ.get("UPI_ID", "yourname@upi")

# Your UPI Name (shown to users)
UPI_NAME = os.environ.get("UPI_NAME", "Your Name")

# MongoDB URL (get free from mongodb.atlas.com)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://user:pass@cluster.mongodb.net/")

# Bot username
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBotUsername")

# Price per OTP (in rupees)
OTP_PRICE = float(os.environ.get("OTP_PRICE", 10))

# Welcome message
START_MESSAGE = os.environ.get("START_MESSAGE", """
👋 Welcome to {name}!

💰 OTP Price: ₹{price} per OTP
📲 UPI: {upi}

Use /buy to purchase balance
Use /balance to check balance
Use /history to see past purchases
""")
