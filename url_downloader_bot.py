import os
import logging
import sys
import time
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

        # Get filename from URL
        try:
            parsed_url = urlparse(url)
            default_filename = os.path.basename(unquote(parsed_url.path))
            if not default_filename:
                default_filename = 'download'
        except:
            default_filename = 'download'

        # Store URL and filename
        self.user_data[chat_id] = {
            'url': url,
            'default_filename': default_filename
        }

        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("Use Default", callback_data="default"),
                InlineKeyboardButton("Rename", callback_data="rename")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send options with filename
        await message.reply_text(
            f"Name: {default_filename}\n"
            "How would you like to upload this?",
            reply_markup=reply_markup
        )

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

        # Clean filename
        new_name = re.sub(r'[^\w\-_\. ]', '', new_name)
        if not new_name:
            await message.reply_text("Invalid filename. Please try again.")
            return

        await self.download_and_send(message, url, new_name)
        del self.user_data[chat_id]

    def format_progress_bar(self, current, total, bars=10):
        progress = (current / total)
        filled_bars = int(round(progress * bars))
        return '█' * filled_bars + '▒' * (bars - filled_bars)

    def format_size(self, size):
        """Format size in bytes to MB"""
        return f"{size / 1024 / 1024:.2f} MB"

    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Starting download...")
        file_path = None

        try:
            # Create download path
            file_path = os.path.join('downloads', f"{message.message_id}_{filename}")
            
            # Start download with progress
            start_time = time.time()
            downloaded_size = 0
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    total_size = int(response.headers.get('content-length', 0))
                    
                    with open(file_path, 'wb') as f:
                        last_update_time = 0
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                current_time = time.time()
                                
                                # Update progress every 0.5 seconds
                                if current_time - last_update_time >= 0.5:
                                    # Calculate progress
                                    progress = (downloaded_size / total_size) * 100
                                    progress_bar = self.format_progress_bar(downloaded_size, total_size)
                                    
                                    # Calculate speed
                                    elapsed_time = current_time - start_time
                                    speed = downloaded_size / elapsed_time if elapsed_time > 0 else 0
                                    
                                    # Calculate ETA
                                    remaining_bytes = total_size - downloaded_size
                                    eta = int(remaining_bytes / speed) if speed > 0 else 0
                                    
                                    # Update status message
                                    status_text = (
                                        f"Downloading: {progress:.2f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{self.format_size(downloaded_size)} of {self.format_size(total_size)}\n"
                                        f"Speed: {self.format_size(speed)}/sec\n"
                                        f"ETA: {eta}s"
                                    )
                                    
                                    try:
                                        await status_message.edit_text(status_text)
                                    except:
                                        pass
                                        
                                    last_update_time = current_time

            # Send file
            await status_message.edit_text("📤 Uploading...")
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