import os
import logging
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot
app = Client(
    "URL_Uploader",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "👋 Hi! I'm a URL Uploader bot.\n\nSend me any direct download link and I'll upload it to Telegram."
    )

@app.on_message(filters.regex(pattern=".*http.*"))
async def url_handler(client, message):
    url = message.text.strip()
    
    # Create keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Use Default", callback_data="default"),
            InlineKeyboardButton("Rename", callback_data="rename")
        ]
    ])
    
    # Get filename from URL
    default_filename = os.path.basename(url)
    if not default_filename:
        default_filename = 'file'
    
    await message.reply_text(
        f"Name: {default_filename}\n"
        "How would you like to upload this?",
        reply_markup=keyboard
    )

async def upload_file(client, message, file_path, filename):
    """Upload file with progress"""
    try:
        start_time = time.time()
        file_size = os.path.getsize(file_path)
        
        # Send initial progress
        status_message = await message.reply_text(
            "Starting Upload...",
            quote=True
        )

        # Progress callback
        async def progress(current, total):
            if total:
                percentage = (current * 100) / total
                speed = current / (time.time() - start_time)
                elapsed_time = round(time.time() - start_time)
                eta = round((total - current) / speed) if speed > 0 else 0
                
                # Create progress bar
                filled_length = int(percentage / 10)
                progress_bar = "■" * filled_length + "□" * (10 - filled_length)

                try:
                    await status_message.edit_text(
                        f"Uploading: {percentage:.2f}%\n"
                        f"[{progress_bar}]\n"
                        f"{current / 1024 / 1024:.2f} MB of {total / 1024 / 1024:.2f} MB\n"
                        f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                        f"ETA: {eta}s"
                    )
                except:
                    pass

        # Upload file with progress
        await message.reply_document(
            document=file_path,
            caption="Here's your file! 📁",
            progress=progress
        )
        
        # Delete progress message
        await status_message.delete()
        
    except Exception as e:
        await message.reply_text(f"❌ Upload failed: {str(e)}")
        logger.error(f"Upload error: {str(e)}")

@app.on_callback_query()
async def callback_handler(client, callback_query):
    if callback_query.data == "default":
        # Handle default name option
        await callback_query.message.edit_text("Using default name...")
        # Add your download and upload logic here
    
    elif callback_query.data == "rename":
        # Handle rename option
        await callback_query.message.edit_text(
            "Please send me the new name for this file:"
        )
        # Add your rename logic here

# Start the bot
if __name__ == "__main__":
    logger.info("Bot is starting...")
    app.run()