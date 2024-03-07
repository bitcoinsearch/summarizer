from datetime import datetime, timedelta
from loguru import logger
import tqdm
import traceback
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader


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

    for dev_url in dev_urls:

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

        docs_list = elastic_search.fetch_data_with_empty_summary(ES_INDEX, dev_url, start_date_str, current_date_str)

        if isinstance(dev_url, list):
            dev_name = dev_url[0].split("/")[-2]
        else:
            dev_name = dev_url.split("/")[-2]

        logger.success(f"Total threads received with empty summary for '{dev_name}': {len(docs_list)}")

        for doc in tqdm.tqdm(docs_list):
            res = None
            try:
                doc_id = doc['_id']
                doc_index = doc['_index']
                if not doc['_source'].get('summary'):
                    xml_summary = xml_reader.get_xml_summary(doc, dev_name)
                    if xml_summary:
                        elastic_search.es_client.update(
                            index=doc_index,
                            id=doc_id,
                            body={
                                'doc': {
                                    "summary": xml_summary
                                }
                            }
                        )
            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")

    logger.success(f"Process complete.")
