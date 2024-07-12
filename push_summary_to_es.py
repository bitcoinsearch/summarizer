from datetime import datetime, timedelta
from loguru import logger
import tqdm
import traceback
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader
from src.utils import log_csv

if __name__ == "__main__":

    APPLY_DATE_RANGE = False

    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient()

    dev_urls = [
        "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/",
        "https://delvingbitcoin.org/",
        "https://gnusha.org/pi/bitcoindev/"
    ]

    error_occurred = False
    error_message = "---"

    try:
        url_status = {}
        for dev_url in dev_urls:
            url_updated_count = set()
            try:
                if APPLY_DATE_RANGE:
                    current_date_str = None
                    if not current_date_str:
                        current_date_str = datetime.now().strftime("%Y-%m-%d")
                    start_date = datetime.now() - timedelta(days=15)
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    logger.info(f"start_date: {start_date_str}")
                    logger.info(f"current_date_str: {current_date_str}")
                else:
                    start_date_str = None
                    current_date_str = None

                docs_list = elastic_search.fetch_data_with_empty_summary(ES_INDEX, dev_url, start_date_str,
                                                                         current_date_str)

                if isinstance(dev_url, list):
                    dev_name = dev_url[0].split("/")[-2]
                else:
                    dev_name = dev_url.split("/")[-2]

                logger.info(f"Total threads received with empty summary for '{dev_name}': {len(docs_list)}")

                for doc in tqdm.tqdm(docs_list):
                    try:
                        doc_id = doc['_id']
                        doc_index = doc['_index']
                        if not doc['_source'].get('summary'):
                            xml_summary = xml_reader.get_xml_summary(doc, dev_name)
                            if xml_summary:
                                res = elastic_search.es_client.update(
                                    index=doc_index,
                                    id=doc_id,
                                    body={
                                        'doc': {
                                            "summary": xml_summary
                                        }
                                    }
                                )
                                url_updated_count.add(res['_id'])
                    except Exception as ex:
                        logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                        logger.warning(doc)

                logger.success(f"Process complete for dev_url: {dev_url}")

            except Exception as ex:
                error_occurred = True
                error_message = str(ex)

            finally:
                log_csv(
                    file_name='push_summary_to_elasticsearch',
                    url=dev_url,
                    updated=len(url_updated_count),
                    error=str(error_occurred),
                    error_log=error_message)

                url_status[dev_url] = {
                    "updated_count": len(url_updated_count),
                    "error_occurred": error_occurred,
                }

        logger.success("Process complete for all domain ")
        logger.info("Summary of updates for all URLs:")
        for url, status in url_status.items():
            logger.info(f"URL:->{url}"
                        f" :: Updated Count: {status['updated_count']} "
                        f" :: Error Occurred: {status['error_occurred']}.")

    except Exception as ex:
        logger.error(f"Error: {str(ex)}\n{traceback.format_exc()}")
