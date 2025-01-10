async def download_and_send(self, message, url, filename):
        status_message = await message.reply_text("⏳ Starting download...")
        file_path = None

        try:
            # Create download path
            file_path = os.path.join('downloads', f"{message.message_id}_{filename}")
            
            # Start download with progress
            start_time = time.time()
            downloaded_size = 0
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    total_size = int(response.headers.get('content-length', 0))
                    
                    with open(file_path, 'wb') as f:
                        last_update_time = 0
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                current_time = time.time()
                                
                                # Update progress every 0.5 seconds
                                if current_time - last_update_time >= 0.5:
                                    progress = (downloaded_size / total_size) * 100
                                    progress_bar = self.format_progress_bar(downloaded_size, total_size)
                                    speed = downloaded_size / (current_time - start_time)
                                    eta = int((total_size - downloaded_size) / speed) if speed > 0 else 0
                                    
                                    status_text = (
                                        f"Downloading: {progress:.2f}%\n"
                                        f"[{progress_bar}]\n"
                                        f"{self.format_size(downloaded_size)} of {self.format_size(total_size)}\n"
                                        f"Speed: {self.format_size(speed)}/sec\n"
                                        f"ETA: {eta}s"
                                    )
                                    
                                    try:
                                        await status_message.edit_text(status_text)
                                    except:
                                        pass
                                        
                                    last_update_time = current_time

            # Start upload
            await status_message.edit_text("📤 Starting upload to Telegram...")
            
            try:
                with open(file_path, 'rb') as f:
                    # Get file size for upload progress
                    f.seek(0, 2)  # Seek to end of file
                    file_size = f.tell()  # Get file size
                    f.seek(0)  # Seek back to beginning
                    
                    # Create upload progress message
                    progress_text = (
                        f"Uploading: 0%\n"
                        f"[▒▒▒▒▒▒▒▒▒▒]\n"
                        f"0 MB of {self.format_size(file_size)}\n"
                        f"Speed: 0 MB/sec\n"
                        f"ETA: calculating..."
                    )
                    await status_message.edit_text(progress_text)
                    
                    upload_start_time = time.time()
                    last_update_time = 0
                    
                    # Create progress callback for upload
                    async def progress_callback(current, total):
                        nonlocal last_update_time
                        current_time = time.time()
                        
                        if current_time - last_update_time >= 0.5:
                            progress = (current / total) * 100
                            progress_bar = self.format_progress_bar(current, total)
                            elapsed_time = current_time - upload_start_time
                            speed = current / elapsed_time if elapsed_time > 0 else 0
                            eta = int((total - current) / speed) if speed > 0 else 0
                            
                            try:
                                await status_message.edit_text(
                                    f"Uploading: {progress:.2f}%\n"
                                    f"[{progress_bar}]\n"
                                    f"{self.format_size(current)} of {self.format_size(total)}\n"
                                    f"Speed: {self.format_size(speed)}/sec\n"
                                    f"ETA: {eta}s"
                                )
                            except:
                                pass
                            
                            last_update_time = current_time
                    
                    # Send document with progress callback
                    await message.reply_document(
                        document=f,
                        filename=filename,
                        caption="Here's your file! 📁",
                        write_timeout=1800,
                        read_timeout=1800,
                        progress=progress_callback
                    )
                
                # Upload completed
                await status_message.delete()
                
            except Exception as upload_error:
                logger.error(f"Upload error: {str(upload_error)}")
                await status_message.edit_text(f"❌ Upload failed: {str(upload_error)}")

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            if status_message:
                await status_message.edit_text(f"❌ Error: {str(e)}")

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing file: {str(e)}")