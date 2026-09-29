import requests
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not BOT_TOKEN:
    print("[ERROR] TELEGRAM_BOT_TOKEN not set in .env")
    exit(1)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

print("[INFO] Fetching updates from Telegram...\n")

try:
    response = requests.get(url, timeout=10)
    data = response.json()

    if not data.get("ok"):
        print("[ERROR] Telegram API returned error:")
        print(data)
        print("\nCheck that BOT_TOKEN is correct.")
        exit(1)

    results = data.get("result", [])

    if not results:
        print("[WARNING] No messages found.")
        print("Make sure:")
        print("  1. The bot has been added to the group")
        print("  2. A message has been sent in the group (e.g. 'hi')")
        print("  3. Then run this script again")
        exit(0)

    print("[SUCCESS] Found groups/chats:\n")
    seen_chat_ids = set()

    for update in results:
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_title = chat.get("title", "(No title - personal chat)")
        chat_type = chat.get("type")

        if chat_id not in seen_chat_ids:
            seen_chat_ids.add(chat_id)
            print(f"  Group/Chat Name : {chat_title}")
            print(f"  Chat Type       : {chat_type}")
            print(f"  Chat ID         : {chat_id}")
            print("  " + "-" * 40)

    print("\n[DONE] Copy the 'Chat ID' value above into your .env file as TELEGRAM_CHAT_ID")

except Exception as e:
    print(f"[ERROR] Something went wrong: {e}")
