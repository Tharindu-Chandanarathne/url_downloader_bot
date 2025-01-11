import os
import logging
from pyrogram import Client, filters

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

logger.info(f"Bot Token Available: {'Yes' if BOT_TOKEN else 'No'}")
logger.info(f"API ID Available: {'Yes' if API_ID else 'No'}")
logger.info(f"API Hash Available: {'Yes' if API_HASH else 'No'}")

# Initialize bot
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    logger.info("Got /start command")
    await message.reply_text("Hello! I'm your bot.")

@app.on_message(filters.private)
async def handle_message(client, message):
    logger.info(f"Got message: {message.text}")
    await message.reply_text("I received your message!")

def main():
    logger.info("Starting bot...")
    app.run()
    logger.info("Bot stopped")

if __name__ == "__main__":
    main()