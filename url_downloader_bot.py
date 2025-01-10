from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import os
import urllib.parse
from pathlib import Path
import asyncio
import aiohttp
import logging
import time
import sys
from dotenv import load_dotenv
import gc
import psutil
import shutil

class URLDownloaderBot:
    def __init__(self, token: str, download_folder: str = "/tmp/downloads"):
        self.token = token
        self.download_folder = download_folder
        os.makedirs(download_folder, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bot.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Clean up old files on start
        self.cleanup_old_files()

    def cleanup_old_files(self):
        """Clean up files older than 1 hour"""
        try:
            # Force garbage collection
            gc.collect()
            
            current_time = time.time()
            for filename in os.listdir(self.download_folder):
                filepath = os.path.join(self.download_folder, filename)
                if os.path.isfile(filepath):
                    if current_time - os.path.getmtime(filepath) > 900:  # 15 minutes
                        os.remove(filepath)
        except Exception as e:
            self.logger.error(f"Cleanup error: {str(e)}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start command"""
        try:
            self.logger.info(f"Start command received from user {update.effective_user.id}")
            welcome_message = (
                "Welcome! 👋\n\n"
                "I can help you download files from direct links.\n"
                "Just send me any direct download link and I'll:\n"
                "1. Download the file\n"
                "2. Send it back to you on Telegram\n\n"
                "Commands:\n"
                "/start - Show this message\n"
                "/help - Get help information\n"
                "/health - Check bot status"
            )
            await update.message.reply_text(welcome_message)
            self.logger.info(f"Start command response sent to user {update.effective_user.id}")
        except Exception as e:
            self.logger.error(f"Error in start_command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again later.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /help command"""
        try:
            help_message = (
                "How to use this bot:\n\n"
                "1. Send any direct download link\n"
                "2. Wait while I download and process the file\n"
                "3. I'll send the file back to you on Telegram\n\n"
                "Note: The link must be a direct download link"
            )
            await update.message.reply_text(help_message)
        except Exception as e:
            self.logger.error(f"Error in help_command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again later.")

    async def healthcheck_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /health command"""
        try:
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
        except Exception as e:
            self.logger.error(f"Error in healthcheck_command: {str(e)}")
            await update.message.reply_text("Error checking health status")

    async def check_file_size(self, url: str) -> int:
        """Check file size before downloading"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to check file size: HTTP {response.status}")
                    
                    file_size = int(response.headers.get('Content-Length', 0))
                    return file_size if file_size > 0 else -1
        except Exception as e:
            self.logger.error(f"Error checking file size: {str(e)}")
            return -1

    async def download_file(self, url: str, message_id: int) -> tuple[str, int]:
        """Download file from URL using aiohttp"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download: HTTP {response.status}")

                content_disposition = response.headers.get('Content-Disposition')
                if content_disposition and 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                else:
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

                return str(safe_filename), int(response.headers.get('Content-Length', 0))

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for URL messages"""
        message = update.message
        url = message.text.strip()

        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid direct download URL.")
            return

        status_message = None
        file_path = None

        try:
            # Send initial status message
            status_message = await message.reply_text("🔍 Checking file size...")
            
            # Check file size
            file_size = await self.check_file_size(url)
            
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

            # Download the file
            file_path, _ = await self.download_file(url, message.message_id)
            
            # Upload to Telegram
            await status_message.edit_text("✅ Download complete! Uploading to Telegram...")
            
            try:
                with open(file_path, 'rb') as file:
                    await message.reply_document(
                        document=file,
                        caption="Here's your file! 📁",
                        write_timeout=1800,  # 30 minutes
                        read_timeout=1800,   # 30 minutes
                        connect_timeout=60   # 1 minute
                    )
                    await status_message.delete()
            except Exception as upload_error:
                self.logger.error(f"Primary upload failed: {str(upload_error)}")
                
                # Try alternative upload method
                try:
                    await status_message.edit_text("⚠️ Retrying upload with alternative method...")
                    with open(file_path, 'rb') as file:
                        await message.reply_document(
                            document=file,
                            filename=os.path.basename(file_path),
                            caption="Here's your file! 📁",
                            write_timeout=1800,
                            read_timeout=1800
                        )
                    await status_message.delete()
                except Exception as alt_error:
                    self.logger.error(f"Alternative upload failed: {str(alt_error)}")
                    await status_message.edit_text("❌ Upload failed. Please try again with a smaller file.")

        except Exception as e:
            error_message = f"Sorry, an error occurred: {str(e)}"
            self.logger.error(f"Error processing URL {url}: {str(e)}")
            if status_message:
                await status_message.edit_text(error_message)
            else:
                await message.reply_text(error_message)
        
        finally:
            # Clean up downloaded file
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    self.logger.error(f"Error removing file {file_path}: {str(e)}")

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
            raise

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