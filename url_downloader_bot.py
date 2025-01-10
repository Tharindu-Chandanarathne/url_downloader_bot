import os
import logging
import sys
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

    def get_filename_from_url(self, url):
        """Extract filename from URL"""
        try:
            # Get filename from URL path
            parsed_url = urlparse(url)
            filename = os.path.basename(unquote(parsed_url.path))
            
            # If no filename in URL, try to get it from query parameters
            if not filename:
                filename = 'download'
            
            # Clean the filename
            filename = re.sub(r'[^\w\-_\. ]', '', filename)
            if not filename:
                filename = 'download'
                
            return filename
        except:
            return 'download'

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        url = message.text.strip()
        chat_id = str(message.chat_id)

        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid direct download URL.")
            return

        # Get and store default filename
        default_filename = self.get_filename_from_url(url)
        self.user_data[chat_id] = {
            'url': url,
            'default_filename': default_filename
        }

        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("📄 Use Default", callback_data="default"),
                InlineKeyboardButton("✏️ Rename", callback_data="rename")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send options message with filename
        status_message = await message.reply_text(
            f"Name: {default_filename}\n\n"
            "How would you like to upload this file?",
            reply_markup=reply_markup
        )
        
        self.user_data[chat_id]['message_id'] = status_message.message_id

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
            await self.process_download(query.message, url)
        elif query.data == "rename":
            # Show default filename when asking for new name
            await query.edit_message_text(
                f"Current name: {default_filename}\n"
                "📝 Send me the new filename:"
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
            await message.reply_text(
                "Invalid filename. Please try again with a valid name.\n"
                f"Current name: {self.user_data[chat_id]['default_filename']}"
            )
            return

        # Start download with new name
        await self.process_download(message, url, new_name)
        
        # Clean up user data
        if chat_id in self.user_data:
            del self.user_data[chat_id]

    async def process_download(self, message, url, custom_filename=None):
        status_message = await message.reply_text("⏳ Starting download...")
        file_path = None

        try:
            # Check file size first
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True) as response:
                    if 'content-length' in response.headers:
                        file_size = int(response.headers['content-length'])
                        if file_size > 2_147_483_648:  # 2GB
                            await status_message.edit_text("❌ File too large (>2GB). Please try a smaller file.")
                            return
                        size_mb = file_size / 1024 / 1024
                        await status_message.edit_text(f"📦 File size: {size_mb:.1f}MB\n⏳ Starting download...")

            # Use custom filename or get from URL
            if custom_filename:
                filename = custom_filename
            else:
                filename = self.get_filename_from_url(url)

            # Create download path
            file_path = os.path.join('downloads', f"{message.message_id}_{filename}")

            # Download file
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await status_message.edit_text(f"❌ Download failed (Status: {response.status})")
                        return

                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

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
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Error processing URL {url}: {str(e)}")
            if status_message:
                await status_message.edit_text(error_msg)

        finally:
            # Clean up
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {str(e)}")

    def run(self):
        """Start the bot."""
        try:
            # Create application
            application = Application.builder().token(self.token).build()

            # Add handlers
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

            # Start polling
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