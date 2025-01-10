import os
import logging
import sys
from urllib.parse import urlparse, unquote
import aiohttp
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import mimetypes
import asyncio
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class URLDownloaderBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get bot token from environment variable
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("BOT_TOKEN not found in environment variables!")
            sys.exit(1)
            
        # Create downloads directory if it doesn't exist
        os.makedirs('downloads', exist_ok=True)
        
        self.logger = logger

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_message = (
            "👋 Welcome to URL Downloader Bot!\n\n"
            "Send me any direct download link, and I'll download and send it back to you.\n"
            "Maximum file size: 2GB"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = (
            "📖 How to use this bot:\n\n"
            "1. Send me a direct download URL\n"
            "2. Wait while I download the file\n"
            "3. I'll send the file back to you\n\n"
            "⚠️ Notes:\n"
            "- Maximum file size: 2GB\n"
            "- Supported protocols: HTTP, HTTPS\n"
            "- Bot times out after 50 minutes\n"
            "- For issues, contact @YourUsername"
        )
        await update.message.reply_text(help_text)

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for URL messages"""
        message = update.message
        url = message.text.strip()
        status_message = None
        file_path = None
        
        try:
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                await message.reply_text("Please send a valid direct download URL.")
                return

            # Send initial status message
            status_message = await message.reply_text("🔍 Checking file size...")
            
            # Check file size
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.head(url, allow_redirects=True) as response:
                        file_size = int(response.headers.get('content-length', 0))
                        
                        if file_size > 2_147_483_648:  # 2GB
                            await status_message.edit_text("❌ File too large (>2GB). Please try a smaller file.")
                            return
                        
                        if file_size > 0:
                            size_mb = file_size / 1024 / 1024
                            await status_message.edit_text(
                                f"📦 File size: {size_mb:.1f}MB\n"
                                f"⏳ Starting download..."
                            )
                        else:
                            await status_message.edit_text(
                                "⚠️ Could not determine file size.\n"
                                "⏳ Starting download anyway..."
                            )
                except Exception as e:
                    logger.error(f"Error checking file size: {str(e)}")
                    await status_message.edit_text("⚠️ Could not check file size. Starting download anyway...")

            # Download the file
            download_path = os.path.join('downloads', f'{message.message_id}_{os.path.basename(url)}')
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(download_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                        
                        # Send the file
                        try:
                            with open(download_path, 'rb') as f:
                                await message.reply_document(
                                    document=f,
                                    caption="Here's your file! 📁",
                                    write_timeout=1800,
                                    read_timeout=1800
                                )
                            if status_message:
                                await status_message.delete()
                        except Exception as e:
                            logger.error(f"Error sending file: {str(e)}")
                            await status_message.edit_text("❌ Error sending file. Please try again.")
                    else:
                        await status_message.edit_text(f"❌ Download failed with status {response.status}")

        except Exception as e:
            error_message = f"Sorry, an error occurred: {str(e)}"
            logger.error(f"Error processing URL {url}: {str(e)}")
            if status_message:
                await status_message.edit_text(error_message)
            else:
                await message.reply_text(error_message)
        
        finally:
            # Clean up downloaded file
            if download_path and os.path.exists(download_path):
                try:
                    os.remove(download_path)
                except Exception as e:
                    logger.error(f"Error removing file {download_path}: {str(e)}")

    def run(self):
        """Start the bot."""
        try:
            # Create the Application
            application = Application.builder().token(self.token).build()

            # Add handlers
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))

            # Start the Bot
            application.run_polling()
            
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            sys.exit(1)

if __name__ == '__main__':
    try:
        logger.info("Starting bot...")
        bot = URLDownloaderBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        sys.exit(1)