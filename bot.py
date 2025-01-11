import os
import logging

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

async def process_download(message, url, filename):
    """Process download and upload with detailed debugging"""
    status_message = await message.reply_text("⏳ Preparing download...")
    file_path = os.path.join('downloads', filename)

    try:
        logger.debug(f"Starting download for URL: {url}")
        
        # Download file
        if await download_file(url, status_message, file_path):
            try:
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    logger.info(f"File downloaded: {file_path} ({file_size / 1024 / 1024:.2f} MB)")
                else:
                    raise FileNotFoundError(f"File not found: {file_path}")

                # Show upload starting
                await status_message.edit_text(
                    "📤 Uploading to Telegram...\n\n"
                    f"File: {filename}\n"
                    f"Size: {file_size / 1024 / 1024:.1f} MB"
                )

                # Upload file
                with open(file_path, 'rb') as f:
                    await message.reply_document(
                        document=f,
                        filename=filename,
                        caption="Here's your file! 📁",
                        write_timeout=7200,
                        read_timeout=7200
                    )
                
                # Delete status message after successful upload
                await status_message.delete()
                logger.info(f"File uploaded successfully: {file_path}")

            except Exception as e:
                logger.error(f"Upload error: {str(e)}")
                await status_message.edit_text(f"❌ Upload failed: {str(e)}")
        else:
            logger.error("Download failed. File not saved.")
    except Exception as e:
        logger.error(f"Download or upload error: {str(e)}")
        await status_message.edit_text(f"❌ Error: {str(e)}")
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File deleted: {file_path}")
        else:
            logger.debug("No file to clean up.")
