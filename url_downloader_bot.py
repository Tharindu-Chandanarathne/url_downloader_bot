import os
import logging
import sys
import time
import asyncio  # Add this import
from datetime import datetime
from urllib.parse import urlparse, unquote
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import re
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

# Rest of your code remains the same

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

        # Database setup
        self.db_url = os.getenv('DATABASE_URL')
        if not self.db_url:
            logger.error("DATABASE_URL not found!")
            sys.exit(1)

        # Initialize database
        self.init_db()

        os.makedirs('downloads', exist_ok=True)
        self.user_data = {}

    def init_db(self):
        """Initialize database tables"""
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    # Create downloads table
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS downloads (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            filename VARCHAR(255),
                            filesize BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Create users table
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT UNIQUE,
                            username VARCHAR(255),
                            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            sys.exit(1)

    # Add these methods to your URLDownloaderBot class

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

    async def handle_new_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        chat_id = str(message.chat_id)

        if chat_id not in self.user_data or not self.user_data[chat_id].get('waiting_for_name'):
            return

        new_name = message.text.strip()
        url = self.user_data[chat_id]['url']

        # Delete the rename message if it exists
        if 'rename_msg_id' in self.user_data[chat_id]:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=self.user_data[chat_id]['rename_msg_id']
                )
            except:
                pass

        # Clean filename
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

    def log_download(self, user_id: int, filename: str, filesize: int):
        """Log download to database"""
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO downloads (user_id, filename, filesize)
                        VALUES (%s, %s, %s)
                    ''', (user_id, filename, filesize))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log download: {str(e)}")

    def update_user(self, user_id: int, username: str):
        """Update user information"""
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO users (user_id, username)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id) 
                        DO UPDATE SET 
                            username = EXCLUDED.username,
                            last_seen = CURRENT_TIMESTAMP
                    ''', (user_id, username))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update user: {str(e)}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        self.update_user(user.id, user.username)
        await update.message.reply_text("👋 Welcome! Send me a URL and I'll download it for you.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Send me a URL and I'll download it for you.")

    async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Preparing download...")
        file_path = None

        try:
            file_path = os.path.join('downloads', filename)
            
            # Download with progress
            if await self.download_file(url, file_path, status_message):
                file_size = os.path.getsize(file_path)
                start_time = time.time()

                try:
                    # First show we're starting the upload
                    progress_text = (
                        f"Uploading: 0%\n"
                        f"[□□□□□□□□□□]\n"
                        f"0 MB of {file_size / 1024 / 1024:.2f} MB\n"
                        f"Speed: calculating...\n"
                        f"ETA: calculating..."
                    )
                    await status_message.edit_text(progress_text)

                    # Start actual file upload
                    with open(file_path, 'rb') as f:
                        # Show progress before actual upload
                        for i in range(0, 95, 5):  # Only go up to 95%
                            uploaded = (i / 100) * file_size
                            elapsed_time = time.time() - start_time
                            speed = uploaded / elapsed_time if elapsed_time > 0 else 0
                            eta = ((file_size - uploaded) / speed) if speed > 0 else 0
                            
                            filled = i // 10
                            progress_bar = "■" * filled + "□" * (10 - filled)
                            
                            progress_text = (
                                f"Uploading: {i}%\n"
                                f"[{progress_bar}]\n"
                                f"{uploaded / 1024 / 1024:.2f} MB of {file_size / 1024 / 1024:.2f} MB\n"
                                f"Speed: {speed / 1024 / 1024:.2f} MB/sec\n"
                                f"ETA: {int(eta)}s"
                            )
                            await status_message.edit_text(progress_text)
                            await asyncio.sleep(0.2)

                        # Actually send the file
                        await message.reply_document(
                            document=f,
                            filename=filename,
                            caption="Here's your file! 📁"
                        )

                        # Show 100% completion briefly
                        final_text = (
                            f"Uploading: 100%\n"
                            f"[■■■■■■■■■■]\n"
                            f"{file_size / 1024 / 1024:.2f} MB of {file_size / 1024 / 1024:.2f} MB\n"
                            f"Speed: {file_size / (time.time() - start_time) / 1024 / 1024:.2f} MB/sec\n"
                            f"ETA: 0s"
                        )
                        await status_message.edit_text(final_text)
                        await asyncio.sleep(20)  # Show completion for 1 second
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

    # [Keep your existing methods for handle_url, button_callback, download_file, etc.]

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

            # Run the bot
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