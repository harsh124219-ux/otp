import sys
from database import add_account


def main():
    if len(sys.argv) < 5:
        print("Usage: python add_account.py <phone> <session_string> <country> <price>")
        print("Example: python add_account.py +919876543210 'SESSION_STRING...' 'INDIA' 150")
        return

    phone = sys.argv[1]
    session = sys.argv[2]
    country = sys.argv[3]
    price = float(sys.argv[4])

    add_account(phone, session, country, price)
    print(f"✅ Account {phone} added to {country} pool at ₹{price}.")


if __name__ == "__main__":
    main()
