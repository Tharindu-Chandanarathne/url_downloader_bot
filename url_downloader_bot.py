from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Define states for the conversation
NAMING_CHOICE = 1
WAITING_FOR_NAME = 2

class URLDownloaderBot:
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for URL messages"""
        message = update.message
        url = message.text.strip()
        
        if not url.startswith(('http://', 'https://')):
            await message.reply_text("Please send a valid direct download URL.")
            return
        
        try:
            # Store URL in context for later use
            context.user_data['current_url'] = url
            
            # Get default filename from URL
            default_filename = os.path.basename(urlparse(url).path)
            if not default_filename:
                default_filename = "download"
            context.user_data['default_filename'] = default_filename
            
            # Check file size first
            status_message = await message.reply_text("🔍 Checking file size...")
            file_size = await self.check_file_size(url)
            
            if file_size > 2_147_483_648:  # 2GB
                await status_message.edit_text("❌ File too large (>2GB). Please try a smaller file.")
                return
            
            # Show file size and naming options
            size_mb = file_size / 1024 / 1024
            keyboard = [
                [
                    InlineKeyboardButton("📄 Use Default", callback_data="use_default"),
                    InlineKeyboardButton("✏️ Rename", callback_data="rename")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_message.edit_text(
                f"📦 File size: {size_mb:.1f}MB\n"
                f"Name: {default_filename}\n\n"
                "How would you like to upload this file?",
                reply_markup=reply_markup
            )
            
            return NAMING_CHOICE
            
        except Exception as e:
            error_message = f"Sorry, an error occurred: {str(e)}"
            self.logger.error(f"Error processing URL {url}: {str(e)}")
            await message.reply_text(error_message)
            return ConversationHandler.END
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button presses"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "use_default":
            # Use default filename
            await self.start_download(
                update, 
                context, 
                context.user_data['current_url'],
                context.user_data['default_filename']
            )
            return ConversationHandler.END
            
        elif query.data == "rename":
            # Ask for new filename
            await query.edit_message_text(
                "Please send me the new filename for this download:"
            )
            return WAITING_FOR_NAME
    
    async def receive_new_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle receiving the new filename"""
        new_name = update.message.text.strip()
        
        # Basic filename sanitization
        new_name = re.sub(r'[^\w\-_\. ]', '', new_name)
        if not new_name:
            await update.message.reply_text("Invalid filename. Please try again with a valid name.")
            return WAITING_FOR_NAME
            
        # Start download with new name
        await self.start_download(
            update, 
            context, 
            context.user_data['current_url'],
            new_name
        )
        return ConversationHandler.END
    
    async def start_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, filename: str):
        """Start the actual download process"""
        message = update.message or update.callback_query.message
        status_message = await message.reply_text("⏳ Starting download...")
        
        try:
            # Download and send file using your existing download logic
            file_path = await self.download_file(url, filename, status_message)
            
            if await self.upload_with_progress(message, file_path, status_message, filename):
                await status_message.delete()
            else:
                await status_message.edit_text("❌ Upload failed. Please try again.")
                
        except Exception as e:
            await status_message.edit_text(f"❌ Error: {str(e)}")
        finally:
            # Clean up
            if 'current_url' in context.user_data:
                del context.user_data['current_url']
            if 'default_filename' in context.user_data:
                del context.user_data['default_filename']
    
    def run(self):
        """Start the bot."""
        try:
            application = Application.builder().token(self.token).build()
            
            # Create conversation handler
            conv_handler = ConversationHandler(
                entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url)],
                states={
                    NAMING_CHOICE: [CallbackQueryHandler(self.button_callback)],
                    WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_new_name)]
                },
                fallbacks=[],
            )
            
            application.add_handler(conv_handler)
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("help", self.help_command))
            
            application.run_polling()
            
        except Exception as e:
            self.logger.error(f"Fatal error: {str(e)}")
            sys.exit(1)