import os
import sys
import time
import logging
import urllib.parse
from pathlib import Path
import asyncio
import aiohttp
import psutil
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class URLDownloaderBot:
    def __init__(self, token: str, download_folder: str = "/tmp/downloads"):
        self.token = token
        self.download_folder = download_folder
        os.makedirs(download_folder, exist_ok=True)
        self.cleanup_old_files()

    def cleanup_old_files(self):
        """Clean up files older than 1 hour"""
        try:
            current_time = time.time()
            for filename in os.listdir(self.download_folder):
                filepath = os.path.join(self.download_folder, filename)
                if os.path.isfile(filepath):
                    if current_time - os.path.getmtime(filepath) > 3600:  # 1 hour
                        os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    def get_size_limit(self) -> int:
        """Return the file size limit in bytes"""
        PREMIUM_BOT = True  # Set to 2GB limit
        return 2_147_483_648 if PREMIUM_BOT else 52_428_800

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start command"""
        welcome_message = (
            "Welcome to URL Downloader Bot! 🚀\n\n"
            "Just send me any direct download link and I'll:\n"
            "1. Download the file\n"
            "2. Upload it to Telegram\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/help - Get help information\n"
            "/health - Check bot status"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /help command"""
        help_message = (
            "How to use this bot:\n\n"
            "1. Send any direct download link\n"
            "2. Wait while I download and process the file\n"
            "3. I'll send the file back to you on Telegram\n\n"
            "Maximum file size: 2GB\n"
            "Supported file types: Any downloadable file"
        )
        await update.message.reply_text(help_message)

    async def healthcheck_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /health command"""
        process = psutil.Process(os.getpid())
        memory_use = process.memory_info().rss / 1024 / 1024  # in MB
        
        status_message = (
            "✅ Bot Status:\n"
            f"Memory Usage: {memory_use:.1f} MB\n"
            f"Uptime: {time.time() - process.create_time():.0f} seconds\n"
            f"Downloads Directory: {self.download_folder}\n"
            f"Files in download dir: {len(os.listdir(self.download_folder))}"
        )
        await update.message.reply_text(status_message)

    async def check_file_size(self, url: str) -> int:
        """Check file size before downloading"""
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as response:
                if response.status != 200:
                    raise Exception(f"Failed to check file size: HTTP {response.status}")
                
                file_size = int(response.headers.get('Content-Length', 0))
                return file_size

    async def download_file(self, url: str, message_id: int) -> tuple[str, int]:
        """Download file from URL using aiohttp"""
        # Check file size first
        file_size = await self.check_file_size(url)
        size_limit = self.get_size_limit()
        
        if file_size > size_limit:
            raise Exception(
                f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds Telegram's limit "
                f"({size_limit / 1024 / 1024:.1f}MB). Cannot upload."
            )
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download: HTTP {response.status}")

                # Get filename from URL or Content-Disposition header
                content_disposition = response.headers.get('Content-Disposition')
                if content_disposition and 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                else:
                    # Remove query parameters from URL
                    clean_url = url.split('?')[0]
                    filename = urllib.parse.unquote(os.path.basename(clean_url))
                    if not filename:
                        filename = f"file_{message_id}"
                
                # Remove any invalid characters from filename
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    filename = filename.replace(char, '')

                # Ensure filename is safe and unique
                safe_filename = Path(self.download_folder) / f"{message_id}_{filename}"
                
                # Download the file
                with open(safe_filename, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

                return str(safe_filename), file_size

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for URL messages"""
        message = update.message
        url = message.text.strip()

        # Clean up old files before new download
        self.cleanup_old_files()
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid direct download URL.")
            return

        try:
            # Send initial status message
            status_message = await message.reply_text("🔍 Checking file size...")
            
            # Check file size first
            try:
                file_size = await self.check_file_size(url)
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
                await status_message.edit_text("⚠️ Could not check file size.\n⏳ Starting download anyway...")

            # Download the file
            file_path, file_size = await self.download_file(url, message.message_id)

            # Update status
            await status_message.edit_text("✅ Download complete! Uploading to Telegram...\nThis might take a while for large files.")
            
            try:
                with open(file_path, 'rb') as file:
                    await message.reply_document(
                        document=file,
                        caption="Here's your file! 📁",
                        write_timeout=1800,  # 30 minutes
                        read_timeout=1800,   # 30 minutes
                        connect_timeout=60,  # 1 minute
                        pool_timeout=1800,   # 30 minutes
                        chunk_size=64 * 1024  # 64KB chunks
                    )
            except Exception as upload_error:
                logger.error(f"Upload error: {str(upload_error)}")
                await status_message.edit_text(f"Error during upload: {str(upload_error)}\nTrying alternative upload method...")
                
                # Alternative upload method for large files
                try:
                    await message.reply_document(
                        document=open(file_path, 'rb'),
                        filename=os.path.basename(file_path),
                        caption="Here's your file! 📁 (Uploaded with alternative method)",
                        write_timeout=1800,
                        read_timeout=1800
                    )
                except Exception as alt_upload_error:
                    raise Exception(f"Both upload methods failed. Last error: {str(alt_upload_error)}")

            # Clean up
            try:
                os.remove(file_path)
            except:
                pass
            await status_message.delete()

        except Exception as e:
            error_message = f"Sorry, an error occurred: {str(e)}"
            logger.error(f"Error processing URL {url}: {str(e)}")
            if 'status_message' in locals():
                await status_message.edit_text(error_message)
            else:
                await message.reply_text(error_message)

    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.token).build()

        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("health", self.healthcheck_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_url
        ))

        # Start the bot
        logger.info("Bot is starting...")
        application.run_polling()

if __name__ == "__main__":
    # Get bot token from environment variable
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("No BOT_TOKEN found in environment variables!")
        
    # Create and run bot
    bot = URLDownloaderBot(BOT_TOKEN)
    
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        # Wait before restarting
        time.sleep(10)
        # Restart the bot
        bot.run()