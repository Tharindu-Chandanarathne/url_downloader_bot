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
        # Load environment variables
        load_dotenv()
        
        # Get bot token
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("BOT_TOKEN not found!")
            sys.exit(1)
            
        # Create downloads directory
        os.makedirs('downloads', exist_ok=True)
        
        self.user_data = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Welcome! Send me a URL and I'll download it for you.\n"
            "Maximum file size: 2GB"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Send me a direct download link and I'll download it for you.\n"
            "You can choose to keep the original filename or rename it."
        )

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        url = message.text.strip()
        chat_id = str(message.chat_id)

        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid direct download URL.")
            return

        # Store URL for this user
        self.user_data[chat_id] = {'url': url}

        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("📄 Use Default Name", callback_data="default"),
                InlineKeyboardButton("✏️ Rename File", callback_data="rename")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send options message
        status_message = await message.reply_text(
            "How would you like to upload this file?",
            reply_markup=reply_markup
        )
        
        # Store message ID for later use
        self.user_data[chat_id]['message_id'] = status_message.message_id

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = str(query.message.chat_id)
        await query.answer()

        if chat_id not in self.user_data:
            await query.edit_message_text("Session expired. Please send the URL again.")
            return

        url = self.user_data[chat_id]['url']
        
        if query.data == "default":
            # Use default name
            await self.process_download(query.message, url)
        elif query.data == "rename":
            # Ask for new name
            await query.edit_message_text(
                "📝 Please send me the new filename for your download:"
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
            await message.reply_text("Invalid filename. Please try again with a valid name.")
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
            # Generate filename
            if custom_filename:
                filename = custom_filename
            else:
                filename = os.path.basename(urlparse(url).path) or 'download'
            
            # Clean filename if needed
            filename = re.sub(r'[^\w\-_\. ]', '', filename)
            if not filename:
                filename = 'download'

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