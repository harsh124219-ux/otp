import asyncio
import logging
import sys
from pyrogram import Client, idle
from info import BOT_TOKEN, API_ID, API_HASH

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)

async def main():
    print("--- DIAGNOSTIC START ---")
    app = Client(
        "diag_session",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN.strip(),
        in_memory=True,
    )
    
    @app.on_raw_update()
    async def raw_h(client, update, users, chats):
        print(f"!!! RECEIVED RAW UPDATE: {type(update).__name__}")

    @app.on_message()
    async def msg_h(client, message):
        print(f"!!! RECEIVED MESSAGE: {message.text}")
        await message.reply("Diagnostic OK")

    async with app:
        me = await app.get_me()
        print(f"Bot connected: @{me.username}")
        print("Waiting for updates... Send a message to the bot now.")
        # Run for 60 seconds or until interrupted
        await idle()  
    print("--- DIAGNOSTIC END ---")

if __name__ == "__main__":
    asyncio.run(main())
