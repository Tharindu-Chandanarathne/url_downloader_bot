import os
import logging
import sys
import time
from datetime import datetime
from urllib.parse import urlparse, unquote
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import re
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

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
                
                try:
                    await status_message.edit_text("📤 Uploading to Telegram...")
                    
                    # Send file
                    with open(file_path, 'rb') as f:
                        await message.reply_document(
                            document=f,
                            filename=filename,
                            caption="Here's your file! 📁"
                        )
                    
                    # Log the download
                    self.log_download(
                        user_id=message.from_user.id,
                        filename=filename,
                        filesize=file_size
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