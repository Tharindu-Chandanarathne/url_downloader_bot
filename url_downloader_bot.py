from pyrogram import Client, filters
import os
import logging
import time
from config import Config

# First update your requirements.txt to include:
# pyrogram
# tgcrypto

class URLUploaderBot:
    def __init__(self):
        self.bot = Client(
            "URL_Uploader",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN
        )

    async def upload_file(self, message, file_path, filename):
        """Upload file with progress"""
        try:
            start_time = time.time()
            file_size = os.path.getsize(file_path)
            
            # Send initial progress
            status_message = await message.reply_text(
                "Starting Upload...",
                quote=True
            )

            # Define progress callback
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
            logging.error(f"Upload error: {str(e)}")