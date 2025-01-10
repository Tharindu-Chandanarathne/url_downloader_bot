import os
from urllib.parse import urlparse, unquote
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
import re
import mimetypes
import asyncio

async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Enhanced handler for URL messages with improved validation, error handling,
    and user feedback.
    """
    message = update.message
    url = message.text.strip()
    status_message = None
    file_path = None
    
    try:
        # Enhanced URL validation
        if not self._is_valid_url(url):
            await message.reply_text(
                "⚠️ Invalid URL format. Please send a valid direct download URL.\n"
                "Supported protocols: HTTP, HTTPS"
            )
            return

        # Send initial status message
        status_message = await message.reply_text(
            "🔍 Analyzing URL...\n"
            "Please wait while I check the file..."
        )

        # Check if URL is accessible
        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(url, allow_redirects=True, timeout=10) as response:
                    if response.status != 200:
                        await status_message.edit_text(
                            f"❌ URL is not accessible (Status: {response.status}).\n"
                            "Please check if the link is valid and try again."
                        )
                        return
                    
                    # Get content type and suggested filename
                    content_type = response.headers.get('content-type', 'application/octet-stream')
                    content_disposition = response.headers.get('content-disposition')
                    file_size = int(response.headers.get('content-length', 0))
                    
                    filename = self._get_filename(url, content_disposition, content_type)
                    
                    # Check file size
                    if file_size > 2_147_483_648:  # 2GB
                        readable_size = self._format_size(file_size)
                        await status_message.edit_text(
                            f"❌ File too large ({readable_size})\n"
                            "Maximum allowed size: 2GB\n"
                            "Please try a smaller file."
                        )
                        return
                    
                    # Update status with file info
                    file_info = (
                        f"📝 File name: {filename}\n"
                        f"📦 Size: {self._format_size(file_size)}\n"
                        f"📎 Type: {content_type}\n"
                        f"⏳ Starting download..."
                    )
                    await status_message.edit_text(file_info)
                    
            except asyncio.TimeoutError:
                await status_message.edit_text(
                    "❌ Request timed out.\n"
                    "The server took too long to respond. Please try again."
                )
                return
            except aiohttp.ClientError as e:
                await status_message.edit_text(
                    f"❌ Connection error: {str(e)}\n"
                    "Please check your URL and try again."
                )
                return

        # Download the file with progress
        try:
            file_path, download_success = await self.download_file(
                url, message.message_id, status_message
            )
            
            if not download_success:
                await status_message.edit_text(
                    "❌ Download failed.\n"
                    "Please check the URL and try again."
                )
                return
            
            # Try primary upload with progress
            upload_success = await self.upload_with_progress(
                message, file_path, status_message
            )
            
            if upload_success:
                await status_message.delete()
            else:
                # Try alternative upload method
                await status_message.edit_text(
                    "⚠️ Primary upload method failed.\n"
                    "Trying alternative method..."
                )
                try:
                    with open(file_path, 'rb') as file:
                        await message.reply_document(
                            document=file,
                            filename=filename,
                            caption="📁 Here's your file!",
                            write_timeout=1800,
                            read_timeout=1800
                        )
                    await status_message.delete()
                except Exception as alt_error:
                    self.logger.error(f"Alternative upload failed: {str(alt_error)}")
                    await status_message.edit_text(
                        "❌ Upload failed.\n"
                        "Please try again with a smaller file or contact support."
                    )
                    
        except Exception as download_error:
            self.logger.error(f"Download error for {url}: {str(download_error)}")
            await status_message.edit_text(
                "❌ Download failed.\n"
                f"Error: {str(download_error)}"
            )
            
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred: {str(e)}"
        self.logger.error(f"Error processing URL {url}: {str(e)}")
        if status_message:
            await status_message.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
    
    finally:
        # Clean up downloaded file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                self.logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                self.logger.error(f"Error removing file {file_path}: {str(e)}")

def _is_valid_url(self, url: str) -> bool:
    """
    Validate URL format and scheme.
    """
    try:
        result = urlparse(url)
        return all([
            result.scheme in ('http', 'https'),
            result.netloc,
            len(url) < 2048  # Common URL length limit
        ])
    except:
        return False

def _get_filename(self, url: str, content_disposition: str = None, content_type: str = None) -> str:
    """
    Extract filename from URL, content disposition, or generate one based on content type.
    """
    filename = None
    
    # Try content disposition first
    if content_disposition:
        try:
            filename = re.findall("filename=(.+)", content_disposition)[0].strip('"')
        except:
            pass
    
    # Try URL path
    if not filename:
        path = unquote(urlparse(url).path)
        filename = os.path.basename(path)
    
    # Generate filename based on content type
    if not filename and content_type:
        ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
        if ext:
            filename = f"download{ext}"
    
    # Fallback
    if not filename:
        filename = "download"
    
    # Sanitize filename
    filename = re.sub(r'[^\w\-_\. ]', '', filename)
    return filename[:255]  # Max filename length

def _format_size(self, size: int) -> str:
    """
    Format file size in human-readable format.
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"