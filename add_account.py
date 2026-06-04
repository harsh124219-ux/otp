import sys
from database import add_account

def main():
    if len(sys.argv) < 4:
        print("Usage: python add_account.py <phone> <session_string> <country>")
        print("Example: python add_account.py +919876543210 'SESSION_STRING...' '🇮🇳 India'")
        return

    phone = sys.argv[1]
    session = sys.argv[2]
    country = sys.argv[3]

    add_account(phone, session, country)
    print(f"✅ Account {phone} added to {country} pool.")

if __name__ == "__main__":
    main()
