import os
import logging
import sys
import time
import asyncio
from urllib.parse import urlparse, unquote
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import re
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class URLDownloaderBot:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("BOT_TOKEN not found!")
            sys.exit(1)
        os.makedirs('downloads', exist_ok=True)
        self.user_data = {}

    def format_size(self, size):
        """Format size in bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

    def create_progress_bar(self, current, total, length=10):
        """Create a progress bar with squares"""
        filled_length = int(length * current // total)
        empty_length = length - filled_length
        bar = '■' * filled_length + '□' * empty_length
        return f"[{bar}]"

    async def download_with_progress(self, url, file_path, message):
        """Download file with progress updates"""
        start_time = time.time()
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        last_update_time = 0
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                total_size = int(response.headers.get('content-length', 0))
                
                with open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress every 0.5 seconds
                            current_time = time.time()
                            if current_time - last_update_time >= 0.5:
                                # Calculate speed
                                elapsed_time = current_time - start_time
                                speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                
                                # Calculate ETA
                                if speed > 0:
                                    eta = (total_size - downloaded) / speed
                                else:
                                    eta = 0
                                
                                # Create progress message
                                progress = (downloaded / total_size) * 100
                                progress_bar = self.create_progress_bar(downloaded, total_size)
                                status_text = (
                                    f"Downloading: {progress:.2f}%\n"
                                    f"{progress_bar}\n"
                                    f"{self.format_size(downloaded)} of {self.format_size(total_size)}\n"
                                    f"Speed: {self.format_size(speed)}/sec\n"
                                    f"ETA: {int(eta)}s"
                                )
                                
                                try:
                                    await message.edit_text(status_text)
                                except Exception as e:
                                    logger.error(f"Error updating progress: {e}")
                                
                                last_update_time = current_time
                
                return True
        return False

    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Starting download...")
        file_path = None

        try:
            # Create download path
            file_path = os.path.join('downloads', f"{message.message_id}_{filename}")

            # Download with progress
            success = await self.download_with_progress(url, file_path, status_message)
            if not success:
                await status_message.edit_text("❌ Download failed")
                return

            # Send file
            await status_message.edit_text("📤 Uploading to Telegram...")
            with open(file_path, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption="Here's your file! 📁",
                    write_timeout=1800,
                    read_timeout=1800
                )
            await status_message.delete()

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            if status_message:
                await status_message.edit_text(f"❌ Error: {str(e)}")

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file: {str(e)}")

    # ... [rest of the code remains the same] ...