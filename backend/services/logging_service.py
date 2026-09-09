import sys
import os
from loguru import logger

def setup_logging():
    # Remove default handler
    logger.remove()
    
    # Custom format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # Console handler
    logger.add(sys.stderr, format=log_format, level="INFO")

    # File handler (backend/data/logs/app.log)
    log_dir = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")
    
    logger.add(
        log_file, 
        rotation="10 MB", 
        retention="10 days", 
        compression="zip", 
        format=log_format, 
        level="DEBUG"
    )

    logger.info("Logging system initialized.")

# Initial setup when imported
setup_logging()
