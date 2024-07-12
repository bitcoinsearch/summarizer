import time
from datetime import datetime, timedelta
import sys
from loguru import logger
import warnings
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import GenerateXML
from src.utils import log_csv
warnings.filterwarnings("ignore")

if __name__ == "__main__":
    error_occurred = False
    error_message = "---"
    dev_urls = [
        "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/",
        "https://delvingbitcoin.org/",
        "https://gnusha.org/pi/bitcoindev/"
    ]
    try:
        gen = GenerateXML()
        elastic_search = ElasticSearchClient()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        # yyyy-mm-dd
        end_date_str = end_date.strftime("%Y-%m-%d")
        start_date_str = start_date.strftime("%Y-%m-%d")
        logger.info(f"start_data: {start_date_str}")
        logger.info(f"end_date_str: {end_date_str}")

        for dev_url in dev_urls:
            try:
                data_list = elastic_search.extract_data_from_es(
                    ES_INDEX, dev_url, start_date_str, end_date_str, exclude_combined_summary_docs=True
                )
                dev_name = dev_url.split("/")[-2]
                logger.success(f"TOTAL THREADS RECEIVED FOR - '{dev_name}': {len(data_list)}")

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

            except Exception as ex:
                logger.error(str(ex))

        logger.success("Process Finished Successfully :)")
        logger.success(f"Error Occurred: {error_occurred}")

    except Exception as ex:
        error_occurred = True
        error_message = str(ex)
        logger.error(f"Error Occurred: {error_occurred}")
        logger.error(f"Error Message: {error_message}")
        logger.error("Process Failed :(")

    finally:
        log_csv(file_name="xmls_generator_production",
                error=str(error_occurred),
                url=dev_urls,
                error_log=error_message
                )

    logger.success("Process Complete.")

