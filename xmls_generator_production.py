import time
import os
from datetime import datetime, timedelta
import sys
from loguru import logger
import warnings
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import GenerateXML
from xml_threading_updater import XMLThreadingUpdater

warnings.filterwarnings("ignore")

if __name__ == "__main__":
    # Get parameters from environment variables
    start_year = os.environ.get('START_YEAR')
    update_threading_only = os.environ.get('UPDATE_THREADING_ONLY', 'false').lower() == 'true'
    
    logger.info(f"🚀 XML GENERATOR: Starting with START_YEAR={start_year}, UPDATE_THREADING_ONLY={update_threading_only}")
    
    # If only updating threading, run the threading updater and exit
    if update_threading_only:
        logger.info("🧵 XML GENERATOR: Running in threading update mode only")
        updater = XMLThreadingUpdater()
        updater.update_all_threading(start_year=start_year)
        logger.info("✅ XML GENERATOR: Threading update completed")
        sys.exit(0)
    
    gen = GenerateXML()
    elastic_search = ElasticSearchClient()
    
    # Only process bitcoin-dev, skip delvingbitcoin as requested
    dev_urls = [
        "https://gnusha.org/pi/bitcoindev/",
        "https://mailing-list.bitcoindevs.xyz/bitcoindev/"
    ]
    
    logger.info("📋 XML GENERATOR: Processing only bitcoin-dev domains (skipping delvingbitcoin)")

    # Calculate date range
    end_date = datetime.now()
    
    if start_year:
        # Use specified year as start date
        start_date = datetime(int(start_year), 1, 1)
        logger.info(f"📅 XML GENERATOR: Using custom start year: {start_year}")
    else:
        # Use default 90 days
        start_date = end_date - timedelta(days=90)
        logger.info("📅 XML GENERATOR: Using default 90 days range")

    # yyyy-mm-dd
    end_date_str = end_date.strftime("%Y-%m-%d")
    start_date_str = start_date.strftime("%Y-%m-%d")
    logger.info(f"start_date: {start_date_str}")
    logger.info(f"end_date_str: {end_date_str}")

    for dev_url in dev_urls:
        data_list = elastic_search.extract_data_from_es(
            ES_INDEX, dev_url, start_date_str, end_date_str, exclude_combined_summary_docs=True
        )
        dev_name = dev_url.split("/")[-2]
        logger.success(f"TOTAL THREADS RECEIVED FOR - '{dev_url}': {len(data_list)}")

        delay = 5
        count_main = 0

        while True:
            try:
                gen.start(data_list, dev_url)
                break
            except (APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError) as ex:
                logger.error(str(ex))
                logger.error(ex)
                time.sleep(delay)
                count_main += 1
                if count_main > 5:
                    sys.exit(ex)

    # After processing, update threading for all XMLs (including newly created ones)
    logger.info("🧵 XML GENERATOR: Starting threading update for all XMLs...")
    try:
        updater = XMLThreadingUpdater()
        updater.update_all_threading(start_year=start_year)
        logger.success("✅ XML GENERATOR: Threading update completed successfully")
    except Exception as e:
        logger.error(f"❌ XML GENERATOR: Error during threading update: {e}")

    logger.info("🎉 Process Complete.")
