import os
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters

# Load environment variables
load_dotenv()

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

if not all([BOT_TOKEN, API_ID, API_HASH]):
    logger.error("Environment variables are missing!")
    exit(1)

# Initialize bot
app = Client(
    name="url_uploader",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text("👋 Hi! I'm alive!")

# Start the bot
if __name__ == "__main__":
    logger.info("Bot is starting...")
    app.run()