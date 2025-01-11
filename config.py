import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class Config:
    # Get values from environment variables
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    API_ID = os.environ.get("API_ID")
    API_HASH = os.environ.get("API_HASH")

    # Raise error if essential variables are missing
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        raise ValueError("BOT_TOKEN is required")
    if not API_ID:
        logger.error("API_ID not found in environment variables")
        raise ValueError("API_ID is required")
    if not API_HASH:
        logger.error("API_HASH not found in environment variables")
        raise ValueError("API_HASH is required")

    # Other configurations
    DOWNLOAD_LOCATION = "./DOWNLOADS"
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 128))
    TG_MAX_FILE_SIZE = 4194304000  # ~4GB limit

    # Create downloads directory if it doesn't exist
    if not os.path.isdir(DOWNLOAD_LOCATION):
        os.makedirs(DOWNLOAD_LOCATION)