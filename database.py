from pymongo import MongoClient
from info import MONGO_URL, ADMIN_ID
from datetime import datetime

client = MongoClient(MONGO_URL)
db = client["otpbot"]

users_col = db["users"]
transactions_col = db["transactions"]
accounts_col = db["accounts"]
orders_col = db["orders"]
config_col = db["config"]


# ── Configuration & Admin Management ─────────

def get_config():
    config = config_col.find_one({"type": "settings"})
    if not config:
        # Initialize default settings
        default_config = {
            "type": "settings",
            "admins": [ADMIN_ID],
            "fsub_channel": None,
            "upi_id": "yourname@upi",
            "upi_name": "Your Name",
            "otp_price": 10.0,
            "updated_at": datetime.now()
        }
        config_col.insert_one(default_config)
        return default_config
    return config

def update_config(key, value):
    config_col.update_one(
        {"type": "settings"},
        {"$set": {key: value, "updated_at": datetime.now()}}
    )

def is_admin(user_id: int):
    config = get_config()
    return user_id in config.get("admins", [])

def add_admin(user_id: int):
    config_col.update_one(
        {"type": "settings"},
        {"$addToSet": {"admins": user_id}}
    )

def remove_admin(user_id: int):
    if user_id == ADMIN_ID: return False # Cannot remove primary admin
    config_col.update_one(
        {"type": "settings"},
        {"$pull": {"admins": user_id}}
    )
    return True


# ── User functions ──────────────────────────

def get_user(user_id: int):
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

def get_balance(user_id: int) -> float:
    user = get_user(user_id)
    return user.get("balance", 0)

def add_balance(user_id: int, amount: float):
    get_user(user_id)
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount}}
    )

def deduct_balance(user_id: int, amount: float) -> bool:
    user = get_user(user_id)
    if user["balance"] >= amount:
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": -amount, "total_spent": amount}}
        )
        return True
    return False


# ── Transaction functions ───────────────────

def add_transaction(user_id: int, utr: str, amount: float, ss_file_id: str):
    transactions_col.insert_one({
        "user_id": user_id,
        "utr": utr,
        "amount": amount,
        "ss_file_id": ss_file_id,
        "status": "pending",
        "timestamp": datetime.now()
    })

def get_transaction(utr: str):
    return transactions_col.find_one({"utr": utr})

def update_transaction_status(utr: str, status: str):
    transactions_col.update_one(
        {"utr": utr},
        {"$set": {"status": status}}
    )

def utr_exists(utr: str) -> bool:
    return transactions_col.find_one({"utr": utr}) is not None


# ── Account Management (Pool) ────────────────

def add_account(phone: str, session_string: str, country: str, price: float):
    accounts_col.update_one(
        {"phone": phone},
        {"$set": {
            "session_string": session_string,
            "country": country.upper(), # Store as uppercase for consistency
            "price": price,
            "status": "available",
            "added_at": datetime.now()
        }},
        upsert=True
    )

def get_available_accounts(country: str = None):
    query = {"status": "available"}
    if country:
        query["country"] = country.upper()
    # Sort by price: Expensive first (descending)
    return list(accounts_col.find(query).sort("price", -1))

def update_account_status(phone: str, status: str):
    accounts_col.update_one({"phone": phone}, {"$set": {"status": status}})


# ── Order Management (Assigned) ──────────────

def create_order(user_id: int, phone: str, session_string: str, country: str, price: float):
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

def get_user_orders(user_id: int):
    return list(orders_col.find({"user_id": user_id}).sort("timestamp", -1))

def get_order(order_id: str):
    return orders_col.find_one({"order_id": order_id})

def close_order(order_id: str):
    orders_col.update_one({"order_id": order_id}, {"$set": {"status": "closed"}})
