import os
import logging
import asyncio
from pyrogram import Client, filters, idle

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

# Create downloads directory if it doesn't exist
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# Initialize bot
app = Client(
    "url_uploader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    workers=6
)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        await message.reply_text(
            "👋 Hi! I'm URL Uploader Bot.\n\n"
            "Send me any direct download link and I'll upload it to Telegram!"
        )
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")

@app.on_message(filters.regex(pattern=".*http.*"))
async def handle_url(client, message):
    try:
        # Simple reply to confirm URL received
        await message.reply_text("📥 URL received! Processing...")
    except Exception as e:
        logger.error(f"Error in URL handler: {str(e)}")

async def main():
    try:
        logger.info("Starting bot...")
        await app.start()
        logger.info("Bot is running...")
        await idle()
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
    except Exception as e:
        logger.error(f"Main loop error: {str(e)}")