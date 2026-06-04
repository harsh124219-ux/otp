from pymongo import MongoClient
from info import MONGO_URL
from datetime import datetime

client = MongoClient(MONGO_URL)
db = client["otpbot"]

users_col = db["users"]
transactions_col = db["transactions"]


# ── User functions ──────────────────────────

def get_user(user_id: int):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({
            "user_id": user_id,
            "balance": 0,
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
            {"$inc": {"balance": -amount}}
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
