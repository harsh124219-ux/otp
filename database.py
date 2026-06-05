from pymongo import MongoClient
from info import MONGO_URL, ADMIN_ID
from datetime import datetime
from pymongo.errors import ConnectionFailure

client = None
db     = None

# FIX BUG 10: Don't assign collections at module level.
# Use get_col() so collections are always fetched from the live db object.
# This means if MongoDB was briefly down at startup, operations still work
# as long as db is initialized before any handler runs.

def init_db():
    global client, db
    try:
        client = MongoClient(MONGO_URL)
        client.admin.command("ismaster")
        db = client["otpbot"]
        print("✅ MongoDB connected successfully!")
    except ConnectionFailure as e:
        print(f"❌ MongoDB connection failed: {e}")
        client = None
        db     = None


init_db()

# ── Collection accessors (always use these, never module-level vars) ──

def _col(name: str):
    """Returns the collection or None if db is unavailable."""
    return db[name] if db is not None else None

# Convenience aliases removed to prevent stale objects. Use _col("name") instead.


# ── Configuration & Admin ────────────────────────────────────

def get_config():
    col = _col("config")
    if col is None:
        return {"admins": [ADMIN_ID]}
    try:
        config = col.find_one({"type": "settings"})
        if not config:
            default = {
                "type":               "settings",
                "admins":             [ADMIN_ID],
                "fsub_channel":       None,
                "upi_id":             "yourname@upi",
                "upi_name":           "Your Name",
                "upi_image_file_id":  None,
                "otp_price":          10.0,
                "recovery_email":     None,
                "admin_2fa":          None,
                "updated_at":         datetime.now(),
            }
            col.insert_one(default)
            return default
        return config
    except Exception as e:
        print(f"❌ Error getting config: {e}")
        return {"admins": [ADMIN_ID]}


def update_config(key, value):
    col = _col("config")
    if col is None:
        return
    try:
        col.update_one(
            {"type": "settings"},
            {"$set": {key: value, "updated_at": datetime.now()}},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Error updating config: {e}")


def is_admin(user_id: int) -> bool:
    config = get_config()
    return user_id in config.get("admins", [ADMIN_ID])


def add_admin(user_id: int):
    col = _col("config")
    if col is None:
        return
    try:
        col.update_one(
            {"type": "settings"},
            {"$addToSet": {"admins": user_id}},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Error adding admin: {e}")


def remove_admin(user_id: int) -> bool:
    col = _col("config")
    if col is None:
        return False
    if user_id == ADMIN_ID:
        return False
    try:
        col.update_one(
            {"type": "settings"},
            {"$pull": {"admins": user_id}}
        )
        return True
    except Exception as e:
        print(f"❌ Error removing admin: {e}")
        return False


# ── Users ────────────────────────────────────────────────────

def get_user(user_id: int):
    col = _col("users")
    if col is None:
        return None
    try:
        user = col.find_one({"user_id": user_id})
        if not user:
            col.insert_one({
                "user_id":     user_id,
                "balance":     0,
                "total_spent": 0,
                "joined":      datetime.now(),
            })
            return col.find_one({"user_id": user_id})
        return user
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None


def get_balance(user_id: int) -> float:
    user = get_user(user_id)
    return user.get("balance", 0) if user else 0


def add_balance(user_id: int, amount: float):
    col = _col("users")
    if col is None:
        return
    try:
        get_user(user_id)
        col.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": amount}}
        )
    except Exception as e:
        print(f"❌ Error adding balance: {e}")


def deduct_balance(user_id: int, amount: float) -> bool:
    col = _col("users")
    if col is None:
        return False
    try:
        user = get_user(user_id)
        if user and user["balance"] >= amount:
            col.update_one(
                {"user_id": user_id},
                {"$inc": {"balance": -amount, "total_spent": amount}}
            )
            return True
        return False
    except Exception as e:
        print(f"❌ Error deducting balance: {e}")
        return False


# ── Transactions ─────────────────────────────────────────────

def add_transaction(user_id: int, utr: str, amount: float, ss_file_id: str):
    col = _col("transactions")
    if col is None:
        return
    try:
        col.insert_one({
            "user_id":    user_id,
            "utr":        utr,
            "amount":     amount,
            "ss_file_id": ss_file_id,
            "status":     "pending",
            "timestamp":  datetime.now(),
        })
    except Exception as e:
        print(f"❌ Error adding transaction: {e}")


def get_transaction(utr: str):
    col = _col("transactions")
    if col is None:
        return None
    try:
        return col.find_one({"utr": utr})
    except Exception as e:
        print(f"❌ Error getting transaction: {e}")
        return None


def update_transaction_status(utr: str, status: str):
    col = _col("transactions")
    if col is None:
        return
    try:
        col.update_one(
            {"utr": utr},
            {"$set": {"status": status}}
        )
    except Exception as e:
        print(f"❌ Error updating transaction status: {e}")


def utr_exists(utr: str) -> bool:
    col = _col("transactions")
    if col is None:
        return False
    try:
        return col.find_one({"utr": utr}) is not None
    except Exception as e:
        print(f"❌ Error checking UTR: {e}")
        return False


# ── Account Pool ─────────────────────────────────────────────

def add_account(
    phone: str, session_string: str, country: str, price: float,
    password: str = "", recovery_email: str = ""
):
    col = _col("accounts")
    if col is None:
        return
    try:
        col.update_one(
            {"phone": phone},
            {"$set": {
                "session_string": session_string,
                "country":        country.upper(),
                "price":          price,
                "status":         "available",
                "password":       password,
                "recovery_email": recovery_email,
                "added_at":       datetime.now(),
            }},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Error adding account: {e}")


def get_available_accounts(country: str = None):
    col = _col("accounts")
    if col is None:
        return []
    try:
        query = {"status": "available"}
        if country:
            query["country"] = country.upper()
        return list(col.find(query).sort("price", 1))
    except Exception as e:
        print(f"❌ Error getting available accounts: {e}")
        return []


def get_accounts_by_country_sorted(country: str, sort_order: str):
    col = _col("accounts")
    if col is None:
        return []
    direction = 1 if sort_order == "low_to_high" else -1
    try:
        return list(
            col.find(
                {"country": country.upper(), "status": "available"}
            ).sort("price", direction)
        )
    except Exception as e:
        print(f"❌ Error fetching sorted accounts: {e}")
        return []


def update_account_status(phone: str, status: str):
    col = _col("accounts")
    if col is None:
        return
    try:
        col.update_one({"phone": phone}, {"$set": {"status": status}})
    except Exception as e:
        print(f"❌ Error updating account status: {e}")


# ── Orders ───────────────────────────────────────────────────

def create_order(user_id: int, phone: str, session_string: str, country: str, price: float):
    col = _col("orders")
    if col is None:
        return None
    try:
        order_id = f"ORD{int(datetime.now().timestamp())}"
        col.insert_one({
            "order_id":       order_id,
            "user_id":        user_id,
            "phone":          phone,
            "session_string": session_string,
            "country":        country,
            "price":          price,
            "status":         "active",
            "timestamp":      datetime.now(),
        })
        return order_id
    except Exception as e:
        print(f"❌ Error creating order: {e}")
        return None


def get_user_orders(user_id: int):
    col = _col("orders")
    if col is None:
        return []
    try:
        return list(col.find({"user_id": user_id}).sort("timestamp", -1))
    except Exception as e:
        print(f"❌ Error getting user orders: {e}")
        return []


def get_order(order_id: str):
    col = _col("orders")
    if col is None:
        return None
    try:
        return col.find_one({"order_id": order_id})
    except Exception as e:
        print(f"❌ Error getting order: {e}")
        return None


def close_order(order_id: str):
    col = _col("orders")
    if col is None:
        return
    try:
        col.update_one(
            {"order_id": order_id},
            {"$set": {"status": "closed"}}
        )
    except Exception as e:
        print(f"❌ Error closing order: {e}")
