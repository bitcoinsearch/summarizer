import os
import sys
import time
import warnings
from datetime import datetime, timedelta

from loguru import logger
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
from tqdm import tqdm

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.gpt_utils import generate_summary_for_transcript
from src.json_utils import GenerateJSON

warnings.filterwarnings("ignore")


def get_json_full_path(base_path, url):
    file_path = url.replace("https://btctranscripts.com/", "")
    full_path = fr"{os.path.join(os.getcwd(), base_path, file_path)}.json"
    return full_path


if __name__ == "__main__":
    APPLY_DATE_RANGE = False

    # Instantiating objects for generating JSON, XML and connecting to ElasticSearch
    gen = GenerateJSON()
    elastic_search = ElasticSearchClient()

    # URLs of mailing lists and forums
    dev_urls = [
        "https://btctranscripts.com/",
    ]

    # Set the date range for data extraction
    if APPLY_DATE_RANGE:
        current_date_str = None
        if not current_date_str:
            current_date_str = datetime.now().strftime("%Y-%m-%d")
        start_date = datetime.now() - timedelta(days=30)
        start_date_str = start_date.strftime("%Y-%m-%d")
        logger.info(f"start_date: {start_date_str}")
        logger.info(f"current_date_str: {current_date_str}")
    else:
        start_date_str = None
        current_date_str = None

    # Process each URL in the dev_urls list
    for dev_url in dev_urls:
        # Fetch data with an empty summary field
        data_list = elastic_search.fetch_raw_data_for_url_with_empty_summary(
            es_index=ES_INDEX, url=dev_url, start_date_str=start_date_str, end_date_str=current_date_str
        )
        dev_name = dev_url.split("/")[-2]
        logger.success(f"TOTAL THREADS RECEIVED FOR - '{dev_name}': {len(data_list)}")

        delay = 5
        count_main = 0
        temp_counter = 0

        while True:
            try:

                BASE_PATH = "static/bitcointranscripts/"
                os.makedirs(BASE_PATH, exist_ok=True)

                for doc in tqdm(data_list):
                    this_id = doc['_id']
                    logger.info(f"{this_id = }")
                    this_data = doc['_source']

                    # Check locally if file exists
                    this_url = this_data['url']
                    json_full_path = get_json_full_path(BASE_PATH, this_url)

                    # Check if the summary exists in a local file
                    if os.path.exists(json_full_path):
                        json_data = gen.load_json_file(json_full_path)
                        this_summary = json_data.get('summary', "")
                        logger.info(f"Summary found in: {json_full_path}")
                    else:
                        this_summary = ""

                    # Generate summary if not found in the locally stored file
                    if not this_summary:
                        speaker = this_data.get('authors', "")
                        this_summary = generate_summary_for_transcript(body=this_data['body'], speaker=speaker)

                    # Update the doc with summary in Elasticsearch Index
                    if this_summary:
                        elastic_search.es_client.update(
                            index=ES_INDEX,
                            id=this_id,
                            body={
                                'doc': {
                                    "summary": this_summary
                                }
                            }
                        )

                    # Update local json file with added summary field
                    this_data['summary'] = this_summary
                    gen.write_json_file(this_data, json_full_path)

                    # Break after N entries
                    temp_counter += 1
                    if temp_counter == 50:
                        logger.info(f"Break statement called after: {temp_counter} entries.")
                        break

                break
            except (APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError) as ex:
                logger.error(str(ex))
                logger.error(ex)
                time.sleep(delay)
                count_main += 1
                if count_main > 5:
                    sys.exit(ex)

    logger.info("Process Complete.")
