import os
import logging
from urllib.parse import urlparse
import aiohttp
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Create downloads directory if not exists
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Store user states
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! 👋\n\n"
        "I'm URL Downloader Bot. Send me any direct link and I'll upload it to Telegram!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Send me any direct download link\n"
        "2. Choose to keep original filename or rename\n"
        "3. Wait for the file to be uploaded\n\n"
        "Supported links:\n"
        "- Direct download links\n"
        "- File hosting links\n\n"
        "Maximum file size: 2GB"
    )

async def download_file(url, status_message, file_path):
    """Download file with progress"""
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
                                speed = downloaded / (now - start_time)
                                eta = (total_size - downloaded) / speed if speed > 0 else 0

                                # Create progress bar
                                filled_length = int(progress / 10)
                                progress_bar = "■" * filled_length + "□" * (10 - filled_length)

                                try:
                                    await status_message.edit_text(
                                        f"Downloading: {progress:.1f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{downloaded / 1024 / 1024:.1f} MB of {total_size / 1024 / 1024:.1f} MB\n"
                                        f"Speed: {speed / 1024 / 1024:.1f} MB/sec\n"
                                        f"ETA: {int(eta)}s"
                                    )
                                except Exception:
                                    pass

                                last_update_time = now

        download_time = int(time.time() - start_time)
        await status_message.edit_text(
            f"Download finished in {download_time}s.\n\n"
            f"File: {os.path.basename(file_path)}\n\n"
            "Now uploading to Telegram..."
        )
        return True
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        await status_message.edit_text(f"Download error: {str(e)}")
        return False

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URLs."""
    message = update.message
    url = message.text.strip()
    chat_id = str(message.chat_id)

    if not url.startswith(('http://', 'https://')):
        await message.reply_text("Please send a valid direct download URL.")
        return

    # Get default filename from URL
    parsed_url = urlparse(url)
    default_filename = os.path.basename(parsed_url.path)
    if not default_filename:
        default_filename = 'download'

    # Store URL data
    user_data[chat_id] = {
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

    await message.reply_text(
        f"Name: {default_filename}\n"
        "How would you like to upload this?",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    await query.answer()

    if chat_id not in user_data:
        await query.edit_message_text("Session expired. Please send the URL again.")
        return

    url = user_data[chat_id]['url']
    default_filename = user_data[chat_id]['default_filename']

    if query.data == "default":
        # Delete the message with buttons
        await query.message.delete()
        # Start download with default filename
        await process_download(query.message, url, default_filename)
        del user_data[chat_id]
    elif query.data == "rename":
        # Delete the message with buttons
        await query.message.delete()
        # Ask for new filename
        user_data[chat_id]['waiting_for_name'] = True
        rename_msg = await query.message.reply_text(
            f"Current name: {default_filename}\n"
            "Send me the new name for this file:"
        )

async def handle_filename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new filename"""
    message = update.message
    chat_id = str(message.chat_id)

    if chat_id not in user_data or not user_data[chat_id].get('waiting_for_name'):
        return

    new_name = message.text.strip()
    url = user_data[chat_id]['url']

    # Clean filename
    new_name = ''.join(c for c in new_name if c.isalnum() or c in '._- ')
    if not new_name:
        await message.reply_text("Invalid filename. Please try again.")
        return

    await process_download(message, url, new_name)
    del user_data[chat_id]

async def process_download(message, url, filename):
    """Process download and upload"""
    status_message = await message.reply_text("⏳ Preparing download...")
    file_path = os.path.join('downloads', filename)

    try:
        # Download file
        if await download_file(url, status_message, file_path):
            try:
                # Upload to Telegram
                await message.reply_document(
                    document=open(file_path, 'rb'),
                    filename=filename,
                    caption="Here's your file! 📁"
                )
                await status_message.delete()
            except Exception as e:
                await status_message.edit_text(f"❌ Upload failed: {str(e)}")
    except Exception as e:
        await status_message.edit_text(f"❌ Error: {str(e)}")
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'https?://[^\s]+'), handle_url
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_filename
    ))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()