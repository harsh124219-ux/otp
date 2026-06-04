from pymongo import MongoClient
from info import MONGO_URL
from datetime import datetime

client = MongoClient(MONGO_URL)
db = client["otpbot"]

users_col = db["users"]
transactions_col = db["transactions"]
accounts_col = db["accounts"] # Pool of available Telegram accounts
orders_col = db["orders"]     # Assigned accounts to users


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

def add_account(phone: str, session_string: str, country: str):
    accounts_col.update_one(
        {"phone": phone},
        {"$set": {
            "session_string": session_string,
            "country": country,
            "status": "available",
            "added_at": datetime.now()
        }},
        upsert=True
    )

def get_available_account(country: str):
    return accounts_col.find_one({"country": country, "status": "available"})

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
