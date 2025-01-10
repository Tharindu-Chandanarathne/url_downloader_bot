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
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Float

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()

class Download(Base):
    __tablename__ = 'downloads'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    filename = Column(String)
    filesize = Column(BigInteger)
    duration = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

class URLDownloaderBot:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("BOT_TOKEN not found!")
            sys.exit(1)

        # Database initialization
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found!")
            sys.exit(1)

        # Convert database URL to async format
        self.db_url = database_url.replace('postgres://', 'postgresql+asyncpg://')
        self.engine = create_async_engine(self.db_url, echo=True)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        os.makedirs('downloads', exist_ok=True)
        self.user_data = {}

    async def init_db(self):
        """Initialize database tables"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def log_download(self, user_id: int, filename: str, filesize: int, duration: float):
        """Log download to database"""
        try:
            async with self.async_session() as session:
                download = Download(
                    user_id=user_id,
                    filename=filename,
                    filesize=filesize,
                    duration=duration
                )
                session.add(download)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log download: {str(e)}")

    async def update_user(self, user_id: int, username: str):
        """Update user information"""
        try:
            async with self.async_session() as session:
                user = await session.get(User, user_id)
                if user:
                    user.username = username
                    user.last_seen = datetime.utcnow()
                else:
                    user = User(
                        user_id=user_id,
                        username=username
                    )
                    session.add(user)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update user: {str(e)}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        await self.update_user(user.id, user.username)
        await update.message.reply_text("👋 Welcome! Send me a URL and I'll download it for you.")

    async def download_and_send(self, message, url, filename):
        start_time = time.time()
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
                    duration = time.time() - start_time
                    await self.log_download(
                        user_id=message.from_user.id,
                        filename=filename,
                        filesize=file_size,
                        duration=duration
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

    # [Keep your existing methods for download_file, button_callback, handle_url, etc.]

    async def run(self):
        """Start the bot with database initialization"""
        try:
            # Initialize database
            await self.init_db()
            
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
            await application.run_polling()

        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            sys.exit(1)

if __name__ == '__main__':
    try:
        logger.info("Starting bot...")
        bot = URLDownloaderBot()
        asyncio.run(bot.run())
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        sys.exit(1)