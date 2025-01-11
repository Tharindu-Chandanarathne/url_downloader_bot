from pymongo import MongoClient
import os
import logging
from urllib.parse import urlparse
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

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "bot_database"

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! 👋\n\n"
        "I'm URL Downloader Bot. Send me any direct link and I'll upload it to Telegram!"
    )

    # Log user to the database
    db.users.update_one(
        {"user_id": user.id},
        {"$set": {"name": user.first_name, "chat_id": update.effective_chat.id}},
        upsert=True
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URLs."""
    message = update.message
    url = message.text.strip()
    chat_id = str(message.chat_id)

    if not url.startswith(('http://', 'https://')):
        await message.reply_text("Please send a valid direct download URL.")
        return

    parsed_url = urlparse(url)
    default_filename = os.path.basename(parsed_url.path) or 'download'

    # Save URL and filename in MongoDB
    db.sessions.update_one(
        {"chat_id": chat_id},
        {"$set": {"url": url, "default_filename": default_filename}},
        upsert=True
    )

    keyboard = [
        [InlineKeyboardButton("Use Default", callback_data="default"),
         InlineKeyboardButton("Rename", callback_data="rename")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        f"Name: {default_filename}\nHow would you like to upload this?",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    await query.answer()

    session = db.sessions.find_one({"chat_id": chat_id})
    if not session:
        await query.edit_message_text("Session expired. Please send the URL again.")
        return

    url = session['url']
    default_filename = session['default_filename']

    if query.data == "default":
        await query.message.delete()
        await process_download(query.message, url, default_filename)
        db.sessions.delete_one({"chat_id": chat_id})
    elif query.data == "rename":
        await query.message.delete()
        db.sessions.update_one(
            {"chat_id": chat_id},
            {"$set": {"waiting_for_name": True}}
        )
        await query.message.reply_text(
            f"Current name: {default_filename}\nSend me the new name for this file:"
        )

async def process_download(message, url, filename):
    """Download and upload logic here"""
    pass  # Keep existing download/upload logic

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'https?://[^\s]+'), handle_url
    ))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()
