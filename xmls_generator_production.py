import time
import os
from datetime import datetime
import sys
from loguru import logger
import warnings
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import GenerateXML

warnings.filterwarnings("ignore")

if __name__ == "__main__":
    gen = GenerateXML()
    elastic_search = ElasticSearchClient()
    dev_urls = [
        # "https://delvingbitcoin.org/",  # Excluded from threading update
        "https://gnusha.org/pi/bitcoindev/",
        "https://mailing-list.bitcoindevs.xyz/bitcoindev/"
    ]

    # Get target year from environment variable, default to current year
    target_year = int(os.getenv("TARGET_YEAR", str(datetime.now().year)))
    logger.info(f"🎯 TARGET YEAR: Processing XMLs for year {target_year}")

    # Set date range for the entire target year
    start_date = datetime(target_year, 1, 1)
    end_date = datetime(target_year, 12, 31)

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
                # Call new method to update threading data only
                gen.update_xml_threading(data_list, dev_url, target_year)
                break
            except (APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError) as ex:
                logger.error(str(ex))
                logger.error(ex)
                time.sleep(delay)
                count_main += 1
                if count_main > 5:
                    sys.exit(ex)

    logger.info("Process Complete.")
