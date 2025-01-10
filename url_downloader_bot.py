import os
import logging
import sys
import time
import asyncio
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
        self.engine = create_async_engine(self.db_url)
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
                async with session.begin():
                    download = Download(
                        user_id=user_id,
                        filename=filename,
                        filesize=filesize,
                        duration=duration
                    )
                    session.add(download)
        except Exception as e:
            logger.error(f"Failed to log download: {str(e)}")

    async def update_user(self, user_id: int, username: str):
        """Update user information"""
        try:
            async with self.async_session() as session:
                async with session.begin():
                    # Using SQLAlchemy 2.0 style
                    result = await session.execute(
                        "SELECT * FROM users WHERE user_id = :user_id",
                        {"user_id": user_id}
                    )
                    user_exists = result.first()
                    
                    if user_exists:
                        await session.execute(
                            """UPDATE users 
                               SET username = :username, last_seen = :now 
                               WHERE user_id = :user_id""",
                            {
                                "username": username,
                                "now": datetime.utcnow(),
                                "user_id": user_id
                            }
                        )
                    else:
                        new_user = User(
                            user_id=user_id,
                            username=username
                        )
                        session.add(new_user)
        except Exception as e:
            logger.error(f"Failed to update user: {str(e)}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        await self.update_user(user.id, user.username)
        await update.message.reply_text("👋 Welcome! Send me a URL and I'll download it for you.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Send me a URL and I'll download it for you.")

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

            # Initialize database and start bot
            async def start_bot():
                await self.init_db()
                await application.run_polling()

            # Run the bot
            asyncio.run(start_bot())

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