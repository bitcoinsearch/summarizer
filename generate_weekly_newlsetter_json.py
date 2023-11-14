import time
import traceback
import openai
from datetime import datetime, timedelta
from loguru import logger
import os
from dotenv import load_dotenv
import sys
import warnings
import json

from src.config import ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX
from generate_homepage_xml import ElasticSearchClient, GenerateJSON

warnings.filterwarnings("ignore")
load_dotenv()

OPENAI_ORG_KEY = os.getenv("OPENAI_ORG_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.organization = OPENAI_ORG_KEY
openai.api_key = OPENAI_API_KEY

if __name__ == "__main__":

    gen = GenerateJSON()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)
    dev_urls = [
        "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/"
    ]

    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")

    start_date = datetime.now() - timedelta(days=7)
    start_date_str = start_date.strftime("%Y-%m-%d")

    end_date = datetime.now() - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")

    logger.info(f"Newsletter publish date: {current_date_str}")
    logger.info(f"Gathering data for newsletter from {start_date_str} to {end_date_str}")

    active_data_list = []
    new_threads_list = []

    for dev_url in dev_urls:
        all_data_df, all_data_list = elastic_search.fetch_all_data_for_url(ES_INDEX, dev_url)
        data_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url, start_date_str, end_date_str)
        dev_name = dev_url.split("/")[-2]
        logger.success(f"TOTAL THREADS RECEIVED FOR '{dev_name}': {len(data_list)}")

        # NEW THREADS POSTS
        seen_titles = set()
        for i in data_list:
            # check if the first post for this title is in past week
            this_title = i['_source']['title']
            if this_title in seen_titles:
                continue
            seen_titles.add(this_title)

            counts, contributors = elastic_search.fetch_contributors_and_threads(
                title=this_title, domain=dev_url, df=all_data_df
            )

            # get the first post's info of this title
            df_title = all_data_df.loc[(all_data_df['title'] == this_title) & (all_data_df['domain'] == dev_url)]
            df_title.sort_values(by='created_at', inplace=True)
            original_post = df_title.iloc[0].to_dict()

            if i['_source']['created_at'] == original_post['created_at']:
                logger.info(f"new thread created on: {original_post['created_at']}, title: {this_title}")
                for author in i['_source']['authors']:
                    contributors.remove(author)
                i['_source']['n_threads'] = counts
                i['_source']['contributors'] = contributors
                i['_source']['dev_name'] = dev_name
                new_threads_list.append(i)
        logger.info(f"number of new threads started this week: {len(new_threads_list)}")

        # TOP ACTIVE POSTS
        active_posts_data = elastic_search.filter_top_active_posts(es_results=data_list, top_n=15,
                                                                   all_data_df=all_data_df)
        logger.info(f"number of filtered top active post: {len(active_posts_data)}")

        new_threads_titles_list = [i['_source']['title'] for i in new_threads_list]

        seen_titles = set()
        active_posts_data_counter = 0
        for data in active_posts_data:
            # if active_posts_data_counter >= 3:
            #     break

            title = data['_source']['title']
            if (title in seen_titles) or (title in new_threads_titles_list):
                continue
            seen_titles.add(title)

            counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url,
                                                                                 df=all_data_df)
            for author in data['_source']['authors']:
                if author in contributors:
                    contributors.remove(author)
            data['_source']['n_threads'] = counts
            data['_source']['contributors'] = contributors
            data['_source']['dev_name'] = dev_name
            active_data_list.append(data)
            active_posts_data_counter += 1
        logger.info(f"number of active posts collected: {len(active_data_list)}")

    # gather ids of docs from json file
    json_file_path = r"static/newsletter.json"
    current_directory = os.getcwd()
    json_full_path = os.path.join(current_directory, json_file_path)
    json_xml_ids = set()
    if os.path.exists(json_full_path):
        with open(json_full_path, 'r') as j:
            json_data = json.load(j)
        json_xml_ids = set(
            [item['title'] for item in json_data['new_threads_this_week']] +
            [item['title'] for item in json_data['active_posts_this_week']]
        )
    else:
        logger.warning(f"No existing newsletter.json file found: {json_full_path}")

    # gather ids of docs from active posts and new thread posts
    filtered_docs_ids = set(
        [gen.get_id(data['_source']['title']) for data in active_data_list] +
        [gen.get_id(data['_source']['title']) for data in new_threads_list]
    )

    # check if there are any updates in xml file
    if filtered_docs_ids != json_xml_ids:
        logger.info("changes found in recent posts ... ")

        delay = 5
        count = 0

        while True:
            try:
                logger.success(f"Total no. of active posts collected: {len(active_data_list)}")
                logger.success(f"Total no. of new threads started this week: {len(new_threads_list)}")

                logger.info("creating newsletter.json file ... ")
                if len(active_data_list) > 0 or len(new_threads_list) > 0:
                    json_file_name = "newsletter.json"
                    new_threads_summary = gen.generate_recent_posts_summary(new_threads_list)

                    new_threads_page_data = []
                    for data in new_threads_list:
                        entry_data = gen.create_single_entry(data, base_url_for_xml="https://tldr.bitcoinsearch.xyz/summary", look_for_combined_summary=True)
                        new_threads_page_data.append(entry_data)

                    active_page_data = []
                    for data in active_data_list:
                        entry_data = gen.create_single_entry(data, base_url_for_xml="https://tldr.bitcoinsearch.xyz/summary", look_for_combined_summary=True)
                        active_page_data.append(entry_data)

                    json_string = {
                        "summary_of_threads_started_this_week": new_threads_summary,
                        "new_threads_this_week": new_threads_page_data,
                        "active_posts_this_week": active_page_data
                    }

                    f_name = f"static/{json_file_name}"
                    with open(f_name, 'w') as f:
                        f.write(json.dumps(json_string, indent=4))
                        logger.success(f"json saved file: {f_name}")

                else:
                    logger.error(f"Data list empty! Please check the data again.")

                break
            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                time.sleep(delay)
                count += 1
                if count > 3:
                    sys.exit(ex)
    else:
        logger.success("No change in the posts, no need to update newsletter.json file")