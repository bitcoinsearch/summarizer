import time
from datetime import datetime, timedelta
import sys
import os
from loguru import logger
from tqdm import tqdm
import warnings
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
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

    gen = GenerateJSON()
    elastic_search = ElasticSearchClient()

    dev_urls = [
        "https://btctranscripts.com/",
    ]

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

    for dev_url in dev_urls:
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

                    # check locally if file exists
                    this_url = this_data['url']
                    json_full_path = get_json_full_path(BASE_PATH, this_url)

                    # check if the summary exists in a local file
                    if os.path.exists(json_full_path):
                        json_data = gen.load_json_file(json_full_path)
                        this_summary = json_data.get('summary', "")
                        logger.info(f"Summary found in: {json_full_path}")
                    else:
                        this_summary = ""

                    # generate summary if not found
                    if not this_summary:
                        speaker = this_data.get('authors', "")
                        this_summary = generate_summary_for_transcript(body=this_data['body'], speaker=speaker)

                    # update ES doc with summary
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

                    # update local json file
                    this_data['summary'] = this_summary
                    gen.write_json_file(this_data, json_full_path)

                    # break after 30 entries
                    temp_counter += 1
                    if temp_counter == 30:
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
