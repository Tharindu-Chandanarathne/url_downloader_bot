from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import os
import urllib.parse
from pathlib import Path
import asyncio
import aiohttp
import logging
import gc  # For garbage collection
import psutil  # For memory management

class URLDownloaderBot:
    def __init__(self, token: str, download_folder: str = "/tmp/downloads"):
        self.token = token
        self.download_folder = download_folder
        os.makedirs(download_folder, exist_ok=True)
        
        # Setup logging to file
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bot.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Clean up old files
        self.cleanup_old_files()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start command"""
        welcome_message = (
            "Welcome to URL Downloader Bot! 🚀\n\n"
            "Just send me any direct download link and I'll:\n"
            "1. Download the file\n"
            "2. Upload it to Telegram\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/help - Get help information"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /help command"""
        help_message = (
            "How to use this bot:\n\n"
            "1. Send any direct download link\n"
            "2. Wait while I download and process the file\n"
            "3. I'll send the file back to you on Telegram\n\n"
            "Note: The link must be a direct download link"
        )
        await update.message.reply_text(help_message)

    def get_size_limit(self) -> int:
        """Return the file size limit in bytes"""
        # Setting max file size to 2GB
        PREMIUM_BOT = True
        return 2_147_483_648 if PREMIUM_BOT else 52_428_800  # 2GB for premium, 50MB for regular

    async def check_file_size(self, url: str) -> int:
        """Check file size before downloading"""
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as response:
                if response.status != 200:
                    raise Exception(f"Failed to check file size: HTTP {response.status}")
                
                # Get file size from headers
                file_size = int(response.headers.get('Content-Length', 0))
                if file_size == 0:
                    # If Content-Length is not provided, we'll need to warn the user
                    return -1
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
        elif file_size == -1:
            # If we couldn't determine size, warn but continue
            self.logger.warning("Could not determine file size before downloading")
        
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
                
                # Get file size
                file_size = int(response.headers.get('Content-Length', 0))

                # Download the file
                with open(safe_filename, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

                return str(safe_filename), file_size

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
            self.logger.error(f"Cleanup error: {str(e)}")
            
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

            # Download the file
            file_path, file_size = await self.download_file(url, message.message_id)

            # Update status
            await status_message.edit_text("✅ Download complete! Uploading to Telegram...")

            # Upload to Telegram with extended timeouts
            await status_message.edit_text("✅ Download complete! Uploading to Telegram...\nThis might take a while for large files.")
            
            success = False
            try:
                with open(file_path, 'rb') as file:
                    await message.reply_document(
                        document=file,
                        caption="Here's your file! 📁",
                        write_timeout=1800,  # 30 minutes
                        read_timeout=1800,   # 30 minutes
                        connect_timeout=60   # 1 minute
                    )
                    success = True
            except Exception as upload_error:
                self.logger.error(f"Upload error: {str(upload_error)}")
                await status_message.edit_text("⚠️ First upload method failed. Trying alternative method...")
                
                try:
                    with open(file_path, 'rb') as file:
                        await message.reply_document(
                            document=file,
                            filename=os.path.basename(file_path),
                            caption="Here's your file! 📁",
                            write_timeout=1800,
                            read_timeout=1800
                        )
                        success = True
                except Exception as alt_upload_error:
                    await status_message.edit_text(f"❌ Upload failed: {str(alt_upload_error)}\nTry with a smaller file.")
            
            finally:
                # Clean up
                if success:
                    await status_message.delete()
                try:
                    os.remove(file_path)
                except Exception as e:
                    self.logger.error(f"Error removing file: {str(e)}")

            # Clean up
            os.remove(file_path)
            await status_message.delete()

        except Exception as e:
            error_message = f"Sorry, an error occurred: {str(e)}"
            self.logger.error(f"Error processing URL {url}: {str(e)}")
            if 'status_message' in locals():
                await status_message.edit_text(error_message)
            else:
                await message.reply_text(error_message)

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

    def run(self):
        """Start the bot"""
        try:
            self.logger.info("Starting bot...")
            
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

            # Log handler registration
            self.logger.info("Handlers registered successfully")

            # Start polling
            self.logger.info("Starting polling...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            self.logger.error(f"Error in run method: {str(e)}")
            raise  # Re-raise the exception for the outer error handler

if __name__ == "__main__":
    try:
        # Load environment variables
        load_dotenv()
        
        # Get bot token from environment variable
        BOT_TOKEN = os.getenv('BOT_TOKEN')
        if not BOT_TOKEN:
            logging.error("No BOT_TOKEN found in environment variables!")
            sys.exit(1)
            
        # Log successful token retrieval    
        logging.info("BOT_TOKEN successfully loaded")
        
        # Create and run bot
        bot = URLDownloaderBot(BOT_TOKEN)
        
        # Continuous operation with error handling
        while True:
            try:
                logging.info("Starting bot instance...")
                bot.run()
            except Exception as e:
                logging.error(f"Bot crashed: {str(e)}")
                logging.info("Waiting 10 seconds before restart...")
                time.sleep(10)
                
    except Exception as e:
        logging.critical(f"Fatal error: {str(e)}")
        sys.exit(1)