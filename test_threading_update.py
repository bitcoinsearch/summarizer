#!/usr/bin/env python3
"""
Test script for the threading update functionality
"""

import os
import sys
from loguru import logger

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from update_threading_structure import ThreadingUpdater

def test_single_file():
    """Test updating a single XML file"""
    updater = ThreadingUpdater()
    
    # Find a sample combined XML file
    sample_files = updater.get_combined_xml_files_by_year(2025)
    
    if not sample_files:
        logger.warning("No combined XML files found for 2025")
        return
    
    # Test with the first file
    sample_file = sample_files[0]
    logger.info(f"Testing with sample file: {sample_file}")
    
    # Extract thread info
    thread_info = updater.extract_thread_info_from_xml(sample_file)
    if thread_info:
        logger.success(f"Successfully extracted thread info: {thread_info['title']}")
        
        # Fetch threading data
        threading_data = updater.fetch_threading_data_for_thread(
            thread_info['title'], 
            thread_info['dev_url']
        )
        
        if threading_data:
            logger.success(f"Found {len(threading_data)} threading items")
            for i, item in enumerate(threading_data[:3]):  # Show first 3
                logger.info(f"  {i+1}: {item['author']} (depth: {item['thread_depth']})")
        else:
            logger.warning("No threading data found")
    else:
        logger.error("Failed to extract thread info")

def test_dry_run():
    """Test dry run mode"""
    logger.info("Testing dry run mode for 2025...")
    updater = ThreadingUpdater()
    updater.process_year(2025, dry_run=True)

if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>")
    
    logger.info("🧪 Starting threading update tests...")
    
    try:
        test_single_file()
        print("\n" + "="*50 + "\n")
        test_dry_run()
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
