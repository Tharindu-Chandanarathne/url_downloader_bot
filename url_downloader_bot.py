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

    async def update_progress(self, current, total, status_message, start_time, is_upload=False):
        try:
            now = time.time()
            elapsed_time = now - start_time
            if elapsed_time == 0:
                elapsed_time = 0.1

            # Calculate progress
            progress = (current / total) * 100 if total > 0 else 0
            
            # Calculate speed
            speed = current / elapsed_time

            # Calculate ETA
            if speed > 0:
                eta = (total - current) / speed
            else:
                eta = 0

            # Create progress bar
            bars = 10
            full_bars = int(progress / (100 / bars))
            empty_bars = bars - full_bars
            bar = "■" * full_bars + "□" * empty_bars

            # Format message
            status_text = (
                f"{'Uploading' if is_upload else 'Downloading'}: {progress:.2f}%\n"
                f"[{bar}]\n"
                f"{current / 1024 / 1024:.2f} MB of {total / 1024 / 1024:.2f} MB\n"
                f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                f"ETA: {int(eta)}s"
            )

            await status_message.edit_text(status_text)
        except Exception as e:
            logger.error(f"Error updating progress: {str(e)}")

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
            await self.download_and_send(query.message, url, default_filename)
            del self.user_data[chat_id]
        elif query.data == "rename":
            await query.edit_message_text(
                f"Current name: {default_filename}\n"
                "Send me the new name for this file:"
            )
            self.user_data[chat_id]['waiting_for_name'] = True

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

    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Preparing download...")
        file_path = None

        try:
            file_path = os.path.join('downloads', f"{message.message_id}_{filename}")
            
            # Download with progress
            if await self.download_file(url, file_path, status_message):
                # Upload with progress
                await status_message.edit_text("📤 Starting upload...")
                upload_start_time = time.time()
                last_update_time = 0
                file_size = os.path.getsize(file_path)

                async def upload_progress(current, total):
                    nonlocal last_update_time
                    now = time.time()
                    if now - last_update_time >= 0.5:
                        await self.update_progress(
                            current,
                            total,
                            status_message,
                            upload_start_time,
                            is_upload=True
                        )
                        last_update_time = now

                # Send file with progress
                with open(file_path, 'rb') as f:
                    await message.reply_document(
                        document=f,
                        filename=filename,
                        caption="Here's your file! 📁",
                        write_timeout=1800,
                        read_timeout=1800,
                        progress=upload_progress
                    )
                await status_message.delete()
            else:
                await status_message.edit_text("❌ Download failed")

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            logger.error(error_msg)
            await status_message.edit_text(error_msg)

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file: {str(e)}")

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