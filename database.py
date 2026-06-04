from pymongo import MongoClient
from info import MONGO_URL, ADMIN_ID
from datetime import datetime

from pymongo.errors import ConnectionFailure

client = None
db = None

def init_db():
    global client, db
    try:
        client = MongoClient(MONGO_URL)
        # The ismaster command is cheap and does not require auth.  It will send a
        # request to the server and raise an exception if connection fails.
        client.admin.command('ismaster')
        db = client["otpbot"]
        print("✅ MongoDB connected successfully!")
    except ConnectionFailure as e:
        print(f"❌ MongoDB connection failed: {e}")
        client = None
        db = None

init_db()

# Ensure collections are only accessed if db is initialized
users_col = db["users"] if db is not None else None
transactions_col = db["transactions"] if db is not None else None
accounts_col = db["accounts"] if db is not None else None
orders_col = db["orders"] if db is not None else None
config_col = db["config"] if db is not None else None





# ── Configuration & Admin Management ─────────

def get_config():
    if config_col is None:
        print("❌ MongoDB not initialized, cannot get config.")
        return {"admins": [ADMIN_ID]} # Return default admin to prevent bot from crashing
    try:
        config = config_col.find_one({"type": "settings"})
        if not config:
            default_config = {
                "type": "settings",
                "admins": [ADMIN_ID],
                "fsub_channel": None,
                "upi_id": "yourname@upi",
                "upi_name": "Your Name",
                "upi_image_file_id": None,   # Telegram file_id for UPI QR/image
                "otp_price": 10.0,
                "recovery_email": None,
                "admin_2fa": None,
                "updated_at": datetime.now()
            }
            config_col.insert_one(default_config)
            return default_config
        return config
    except Exception as e:
        print(f"❌ Error getting config: {e}")
        return {"admins": [ADMIN_ID]} # Return default admin to prevent bot from crashing


def update_config(key, value):
    if config_col is None:
        print("❌ MongoDB not initialized, cannot update config.")
        return
    try:
        config_col.update_one(
            {"type": "settings"},
            {"$set": {key: value, "updated_at": datetime.now()}}
        )
    except Exception as e:
        print(f"❌ Error updating config: {e}")


def is_admin(user_id: int):
    from info import ADMIN_ID
    config = get_config()
    return user_id in config.get("admins", [ADMIN_ID])

def add_admin(user_id: int):
    if config_col is None:
        print("❌ MongoDB not initialized, cannot add admin.")
        return
    try:
        config_col.update_one(
            {"type": "settings"},
            {"$addToSet": {"admins": user_id}}
        )
    except Exception as e:
        print(f"❌ Error adding admin: {e}")


def remove_admin(user_id: int):
    if config_col is None:
        print("❌ MongoDB not initialized, cannot remove admin.")
        return False
    if user_id == ADMIN_ID:
        return False
    try:
        config_col.update_one(
            {"type": "settings"},
            {"$pull": {"admins": user_id}}
        )
        return True
    except Exception as e:
        print(f"❌ Error removing admin: {e}")
        return False



# ── User functions ──────────────────────────

def get_user(user_id: int):
    if users_col is None:
        print("❌ MongoDB not initialized, cannot get user.")
        return None
    try:
        user = users_col.find_one({"user_id": user_id})
        if not user:
            users_col.insert_one({
                "user_id": user_id,
                "balance": 0,
                "total_spent": 0,
                "joined": datetime.now()
            })
            return users_col.find_one({"user_id": user_id})
        return user
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None


def get_balance(user_id: int) -> float:
    user = get_user(user_id)
    return user.get("balance", 0) if user else 0

def add_balance(user_id: int, amount: float):
    if users_col is None:
        print("❌ MongoDB not initialized, cannot add balance.")
        return
    try:
        get_user(user_id)
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": amount}}
        )
    except Exception as e:
        print(f"❌ Error adding balance: {e}")


def deduct_balance(user_id: int, amount: float) -> bool:
    if users_col is None:
        print("❌ MongoDB not initialized, cannot deduct balance.")
        return False
    try:
        user = get_user(user_id)
        if user and user["balance"] >= amount:
            users_col.update_one(
                {"user_id": user_id},
                {"$inc": {"balance": -amount, "total_spent": amount}}
            )
            return True
        return False
    except Exception as e:
        print(f"❌ Error deducting balance: {e}")
        return False



# ── Transaction functions ───────────────────

def add_transaction(user_id: int, utr: str, amount: float, ss_file_id: str):
    if transactions_col is None:
        print("❌ MongoDB not initialized, cannot add transaction.")
        return
    try:
        transactions_col.insert_one({
            "user_id": user_id,
            "utr": utr,
            "amount": amount,
            "ss_file_id": ss_file_id,
            "status": "pending",
            "timestamp": datetime.now()
        })
    except Exception as e:
        print(f"❌ Error adding transaction: {e}")


def get_transaction(utr: str):
    if transactions_col is None:
        print("❌ MongoDB not initialized, cannot get transaction.")
        return None
    try:
        return transactions_col.find_one({"utr": utr})
    except Exception as e:
        print(f"❌ Error getting transaction: {e}")
        return None


def update_transaction_status(utr: str, status: str):
    if transactions_col is None:
        print("❌ MongoDB not initialized, cannot update transaction status.")
        return
    try:
        transactions_col.update_one(
            {"utr": utr},
            {"$set": {"status": status}}
        )
    except Exception as e:
        print(f"❌ Error updating transaction status: {e}")


def utr_exists(utr: str) -> bool:
    if transactions_col is None:
        print("❌ MongoDB not initialized, UTR cannot exist.")
        return False
    try:
        return transactions_col.find_one({"utr": utr}) is not None
    except Exception as e:
        print(f"❌ Error checking UTR existence: {e}")
        return False



# ── Account Management (Pool) ────────────────

def add_account(phone: str, session_string: str, country: str, price: float):
    if accounts_col is None:
        print("❌ MongoDB not initialized, cannot add account.")
        return
    try:
        accounts_col.update_one(
            {"phone": phone},
            {"$set": {
                "session_string": session_string,
                "country": country.upper(),
                "price": price,
                "status": "available",
                "added_at": datetime.now()
            }},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Error adding account: {e}")


def get_available_accounts(country: str = None):
    if accounts_col is None:
        print("❌ MongoDB not initialized, cannot get available accounts.")
        return []
    try:
        query = {"status": "available"}
        if country:
            query["country"] = country.upper()
        return list(accounts_col.find(query).sort("price", -1))
    except Exception as e:
        print(f"❌ Error getting available accounts: {e}")
        return []


def update_account_status(phone: str, status: str):
    if accounts_col is None:
        print("❌ MongoDB not initialized, cannot update account status.")
        return
    try:
        accounts_col.update_one({"phone": phone}, {"$set": {"status": status}})
    except Exception as e:
        print(f"❌ Error updating account status: {e}")



# ── Order Management (Assigned) ──────────────

def create_order(user_id: int, phone: str, session_string: str, country: str, price: float):
    if orders_col is None:
        print("❌ MongoDB not initialized, cannot create order.")
        return None
    try:
        order_id = f"ORD{int(datetime.now().timestamp())}"
        orders_col.insert_one({
            "order_id": order_id,
            "user_id": user_id,
            "phone": phone,
            "session_string": session_string,
            "country": country,
            "price": price,
            "status": "active",
            "timestamp": datetime.now()
        })
        return order_id
    except Exception as e:
        print(f"❌ Error creating order: {e}")
        return None


def get_user_orders(user_id: int):
    if orders_col is None:
        print("❌ MongoDB not initialized, cannot get user orders.")
        return []
    try:
        return list(orders_col.find({"user_id": user_id}).sort("timestamp", -1))
    except Exception as e:
        print(f"❌ Error getting user orders: {e}")
        return []


def get_order(order_id: str):
    if orders_col is None:
        print("❌ MongoDB not initialized, cannot get order.")
        return None
    try:
        return orders_col.find_one({"order_id": order_id})
    except Exception as e:
        print(f"❌ Error getting order: {e}")
        return None


def close_order(order_id: str):
    if orders_col is None:
        print("❌ MongoDB not initialized, cannot close order.")
        return
    try:
        orders_col.update_one({"order_id": order_id}, {"$set": {"status": "closed"}})
    except Exception as e:
        print(f"❌ Error closing order: {e}")
