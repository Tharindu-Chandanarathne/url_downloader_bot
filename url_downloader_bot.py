import asyncio
import os
import logging
import sys
import time
import math
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
        self.download_states = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! Send me a URL and I'll download it for you.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Send me a URL and I'll download it for you.")

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        url = message.text.strip()
        chat_id = str(message.chat_id)

        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid URL")
            return

        try:
            parsed_url = urlparse(url)
            default_filename = os.path.basename(unquote(parsed_url.path))
            if not default_filename:
                default_filename = 'download'
        except:
            default_filename = 'download'

        self.user_data[chat_id] = {
            'url': url,
            'default_filename': default_filename
        }

        keyboard = [
            [
                InlineKeyboardButton("Use Default", callback_data="default"),
                InlineKeyboardButton("Rename", callback_data="rename")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"Name: {default_filename}\n"
            "How would you like to upload this?",
            reply_markup=reply_markup
        )

    async def monitor_upload_progress(self, original_size, temp_upload_path, status_message):
        """Monitor upload progress by checking file size"""
        start_time = time.time()
        last_update_time = 0

        while os.path.exists(temp_upload_path):
            current_time = time.time()
            if current_time - last_update_time >= 0.5:  # Update every 0.5 seconds
                # Calculate remaining size
                remaining_size = original_size - os.path.getsize(temp_upload_path)
                uploaded_size = original_size - remaining_size
                
                # Calculate progress
                progress = (uploaded_size / original_size) * 100
                elapsed_time = current_time - start_time
                speed = uploaded_size / elapsed_time if elapsed_time > 0 else 0
                eta = int(remaining_size / speed) if speed > 0 else 0

                # Create progress bar
                progress_bars = 10
                filled = int(progress / (100 / progress_bars))
                progress_bar = "■" * filled + "□" * (progress_bars - filled)

                status_text = (
                    f"Uploading: {progress:.2f}%\n"
                    f"[{progress_bar}]\n"
                    f"{uploaded_size / 1024 / 1024:.2f} MB of {original_size / 1024 / 1024:.2f} MB\n"
                    f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                    f"ETA: {eta}s"
                )
                
                try:
                    await status_message.edit_text(status_text)
                except:
                    pass

                last_update_time = current_time
            
            await asyncio.sleep(0.1)  # Small delay to prevent high CPU usage

    
    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Preparing download...")
        file_path = None

        try:
            file_path = os.path.join('downloads', filename)
            
            # Download with progress
            if await self.download_file(url, file_path, status_message):
                try:
                    # Get file size for upload progress tracking
                    file_size = os.path.getsize(file_path)
                    start_time = time.time()
                    uploaded = 0
                    
                    # Update initial upload status
                    progress_text = (
                        f"Uploading: 0%\n"
                        f"[□□□□□□□□□□]\n"
                        f"0 MB of {file_size / 1024 / 1024:.2f} MB\n"
                        f"Speed: calculating...\n"
                        f"ETA: calculating..."
                    )
                    await status_message.edit_text(progress_text)

                    # Send file
                    with open(file_path, 'rb') as f:
                        await message.reply_document(
                            f,
                            caption="Here's your file! 📁"
                        )
                    
                    await status_message.delete()

                except Exception as upload_error:
                    logger.error(f"Upload error: {str(upload_error)}")
                    await status_message.edit_text(f"❌ Upload failed: {str(upload_error)}")
            else:
                await status_message.edit_text("❌ Download failed")

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            logger.error(error_msg)
            if status_message:
                await status_message.edit_text(error_msg)

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file: {str(e)}")

    async def download_file(self, url, file_path, status_message):
        try:
            start_time = time.time()
            last_update_time = 0

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_message.edit_text(f"Download failed with status {response.status}")
                        return False

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                
                                if now - last_update_time >= 0.5:
                                    progress = (downloaded / total_size) * 100
                                    elapsed_time = now - start_time
                                    speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                    eta = int((total_size - downloaded) / speed) if speed > 0 else 0

                                    # Create progress bar
                                    progress_bars = 10
                                    filled = int(progress / (100 / progress_bars))
                                    progress_bar = "■" * filled + "□" * (progress_bars - filled)

                                    status_text = (
                                        f"Downloading: {progress:.2f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{downloaded / 1024 / 1024:.2f} MB of {total_size / 1024 / 1024:.2f} MB\n"
                                        f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                                        f"ETA: {eta}s"
                                    )
                                    
                                    try:
                                        await status_message.edit_text(status_text)
                                    except:
                                        pass

                                    last_update_time = now

            download_time = int(time.time() - start_time)
            await status_message.edit_text(
                f"Download finish in {download_time}s.\n\n"
                f"File: {os.path.basename(file_path)}\n\n"
                "Now uploading to Telegram..."
            )
            return True
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            await status_message.edit_text(f"Download error: {str(e)}")
            return False

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = str(query.message.chat_id)
        await query.answer()

        if chat_id not in self.user_data:
            await query.edit_message_text("Session expired. Please send the URL again.")
            return

        url = self.user_data[chat_id]['url']
        default_filename = self.user_data[chat_id]['default_filename']

        if query.data == "default":
            # Delete the message with buttons
            await query.message.delete()
            # Start download with default filename
            await self.download_and_send(query.message, url, default_filename)
            del self.user_data[chat_id]
        elif query.data == "rename":
            # Delete the message with buttons
            await query.message.delete()
            # Send new message asking for filename
            rename_msg = await query.message.reply_text(
                f"Current name: {default_filename}\n"
                "Send me the new name for this file:"
            )
            self.user_data[chat_id]['waiting_for_name'] = True
            self.user_data[chat_id]['rename_msg_id'] = rename_msg.message_id

    async def handle_new_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        chat_id = str(message.chat_id)

        if chat_id not in self.user_data or not self.user_data[chat_id].get('waiting_for_name'):
            return

        new_name = message.text.strip()
        url = self.user_data[chat_id]['url']

        # Clean filename
        new_name = re.sub(r'[^\w\-_\. ]', '', new_name)
        if not new_name:
            await message.reply_text("Invalid filename. Please try again.")
            return

        # Delete the rename message if it exists
        if 'rename_msg_id' in self.user_data[chat_id]:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=self.user_data[chat_id]['rename_msg_id']
                )
            except:
                pass  # Message might already be deleted

        await self.download_and_send(message, url, new_name)
        del self.user_data[chat_id]

    async def handle_new_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        chat_id = str(message.chat_id)

        if chat_id not in self.user_data or not self.user_data[chat_id].get('waiting_for_name'):
            return

        new_name = message.text.strip()
        url = self.user_data[chat_id]['url']

        new_name = re.sub(r'[^\w\-_\. ]', '', new_name)
        if not new_name:
            await message.reply_text("Invalid filename. Please try again.")
            return

        await self.download_and_send(message, url, new_name)
        del self.user_data[chat_id]

    async def download_file(self, url, file_path, status_message):
        try:
            start_time = time.time()
            last_update_time = 0

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_message.edit_text(f"Download failed with status {response.status}")
                        return False

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                
                                if now - last_update_time >= 0.5:
                                    await self.update_progress(
                                        downloaded, 
                                        total_size, 
                                        status_message, 
                                        start_time
                                    )
                                    last_update_time = now

            # Calculate total download time
            download_time = int(time.time() - start_time)
            filename = os.path.basename(file_path)
            
            # Show completion message
            await status_message.edit_text(
                f"Download finish in {download_time}s.\n\n"
                f"File: {filename}\n\n"
                "Now uploading to Telegram..."
            )
            return True
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            await status_message.edit_text(f"Download error: {str(e)}")
            return False

    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Preparing download...")
        file_path = None
        upload_status = {}  # To store upload status

        try:
            file_path = os.path.join('downloads', filename)
            
            # Download with progress
            if await self.download_file(url, file_path, status_message):
                file_size = os.path.getsize(file_path)
                
                # Initialize upload status
                upload_status['start_time'] = time.time()
                upload_status['last_update_time'] = 0
                upload_status['uploaded_size'] = 0

                # Create callback for upload progress
                async def upload_callback(current, total):
                    try:
                        now = time.time()
                        if now - upload_status['last_update_time'] >= 0.5:  # Update every 0.5 seconds
                            # Calculate progress
                            progress = (current / total) * 100
                            elapsed_time = now - upload_status['start_time']
                            speed = current / elapsed_time if elapsed_time > 0 else 0
                            eta = int((total - current) / speed) if speed > 0 else 0

                            # Create progress bar
                            filled = int(progress / 10)
                            progress_bar = "■" * filled + "□" * (10 - filled)

                            status_text = (
                                f"Uploading: {progress:.2f}%\n"
                                f"[{progress_bar}]\n"
                                f"{current / 1024 / 1024:.2f} MB of {total / 1024 / 1024:.2f} MB\n"
                                f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                                f"ETA: {eta}s"
                            )

                            await status_message.edit_text(status_text)
                            upload_status['last_update_time'] = now
                    except Exception as e:
                        logger.error(f"Error in upload callback: {str(e)}")

                # Send file with progress callback
                with open(file_path, 'rb') as f:
                    try:
                        await message.reply_document(
                            document=f,
                            filename=filename,
                            caption="Here's your file! 📁",
                            write_timeout=3600,  # 1 hour timeout
                            read_timeout=3600,
                            progress=upload_callback
                        )
                        await status_message.delete()
                    except Exception as upload_error:
                        logger.error(f"Upload error: {str(upload_error)}")
                        await status_message.edit_text(f"❌ Upload failed: {str(upload_error)}")
            else:
                await status_message.edit_text("❌ Download failed")

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            logger.error(error_msg)
            if status_message:
                await status_message.edit_text(error_msg)

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file: {str(e)}")

    async def download_file(self, url, file_path, status_message):
        try:
            start_time = time.time()
            last_update_time = 0

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_message.edit_text(f"Download failed with status {response.status}")
                        return False

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                
                                if now - last_update_time >= 0.5:
                                    progress = (downloaded / total_size) * 100
                                    elapsed_time = now - start_time
                                    speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                    eta = int((total_size - downloaded) / speed) if speed > 0 else 0

                                    progress_bar = "■" * int(progress / 10) + "□" * (10 - int(progress / 10))

                                    status_text = (
                                        f"Downloading: {progress:.2f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{downloaded / 1024 / 1024:.2f} MB of {total_size / 1024 / 1024:.2f} MB\n"
                                        f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                                        f"ETA: {eta}s"
                                    )
                                    
                                    try:
                                        await status_message.edit_text(status_text)
                                    except:
                                        pass

                                    last_update_time = now

            download_time = int(time.time() - start_time)
            await status_message.edit_text(
                f"Download finish in {download_time}s.\n\n"
                f"File: {os.path.basename(file_path)}\n\n"
                "Now uploading to Telegram..."
            )
            return True
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            await status_message.edit_text(f"Download error: {str(e)}")
            return False
    async def download_file(self, url, file_path, status_message):
        try:
            start_time = time.time()
            last_update_time = 0

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_message.edit_text(f"Download failed with status {response.status}")
                        return False

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                
                                if now - last_update_time >= 0.5:
                                    progress = (downloaded / total_size) * 100
                                    elapsed_time = now - start_time
                                    speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                    eta = int((total_size - downloaded) / speed) if speed > 0 else 0

                                    # Create progress bar
                                    progress_bars = 10
                                    filled = int(progress / (100 / progress_bars))
                                    progress_bar = "■" * filled + "□" * (progress_bars - filled)

                                    status_text = (
                                        f"Downloading: {progress:.2f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{downloaded / 1024 / 1024:.2f} MB of {total_size / 1024 / 1024:.2f} MB\n"
                                        f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                                        f"ETA: {eta}s"
                                    )
                                    
                                    try:
                                        await status_message.edit_text(status_text)
                                    except:
                                        pass

                                    last_update_time = now

            download_time = int(time.time() - start_time)
            await status_message.edit_text(
                f"Download finish in {download_time}s.\n\n"
                f"File: {os.path.basename(file_path)}\n\n"
                "Now uploading to Telegram..."
            )
            return True
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            await status_message.edit_text(f"Download error: {str(e)}")
            return False

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def create_progress_bar(self, current, total, length=10):
        filled_length = int(length * current / total)
        return "■" * filled_length + "□" * (length - filled_length)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def create_progress_bar(self, current, total, length=10):
        filled_length = int(length * current / total)
        return "■" * filled_length + "□" * (length - filled_length)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def create_progress_bar(self, current, total, length=10):
        filled_length = int(length * current / total)
        return "■" * filled_length + "□" * (length - filled_length)

    def run(self):
        try:
            application = Application.builder().token(self.token).build()

            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CallbackQueryHandler(self.button_callback))
            application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
                self.handle_url
            ))
            application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'https?://'),
                self.handle_new_name
            ))

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