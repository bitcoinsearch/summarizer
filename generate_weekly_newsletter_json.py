import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

from loguru import logger
from tqdm import tqdm

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.json_utils import GenerateJSON
from src.utils import month_dict
from src.xml_utils import GenerateXML

if __name__ == "__main__":

    # Instantiating objects for generating JSON, XML and connecting to ElasticSearch
    json_gen = GenerateJSON()
    xml_gen = GenerateXML()
    elastic_search = ElasticSearchClient()

    # URLs for development mailing lists and forums
    dev_urls = [
        ["https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
         "https://gnusha.org/pi/bitcoindev/"],
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/",
        "https://delvingbitcoin.org/"
    ]

    # Set the date range for data extraction: last week to yesterday.
    current_date = datetime.now()
    start_date = current_date - timedelta(days=7)
    end_date = current_date - timedelta(days=1)

    current_date_str = current_date.strftime("%Y-%m-%d")
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    logger.info(f"Newsletter publish date: {current_date_str}")
    logger.info(f"Gathering data for newsletter from {start_date_str} to {end_date_str}")

    # Convert month from number to name for filename construction
    month_name = month_dict[int(current_date.month)]
    str_month_year = f"{month_name}_{int(current_date.year)}"

    active_data_list = []
    new_threads_list = []

    # Process each URL in the dev_urls list
    for dev_url in dev_urls:
        data_list = elastic_search.extract_data_from_es(
            ES_INDEX, dev_url, start_date_str, end_date_str, exclude_combined_summary_docs=True
        )

        dev_name = dev_url[0].split("/")[-2] if isinstance(dev_url, list) else dev_url.split("/")[-2]
        logger.success(f"Retrieved {len(data_list)} threads for {dev_name}")

        # NEW THREADS POSTS
        seen_titles = set()
        for i in data_list:
            this_title = i['_source']['title']
            if this_title in seen_titles:
                continue
            seen_titles.add(this_title)

            # Check if any new thread started in given week
            if i['_source']['type'] == 'original_post':
                logger.success(f"New thread created on: {i['_source']['created_at']} || TITLE: {this_title}")

                counts, contributors = elastic_search.es_fetch_contributors_and_threads(
                    es_index=ES_INDEX, title=this_title, domain=dev_url
                )
                # Separate an original author and contributors
                for author in i['_source']['authors']:
                    contributors.remove(author)
                i['_source']['n_threads'] = counts
                i['_source']['contributors'] = contributors
                i['_source']['dev_name'] = dev_name
                new_threads_list.append(i)
        logger.info(f"No. of new threads started this week: {len(new_threads_list)}")

        # TOP ACTIVE POSTS
        active_posts_data = elastic_search.filter_top_active_posts(es_results=data_list, top_n=15)
        logger.info(f"No. of filtered top active post: {len(active_posts_data)}")

        new_threads_titles_list = [i['_source']['title'] for i in new_threads_list]

        seen_titles = set()
        # active_posts_data_counter = 0
        for data in active_posts_data:
            # if active_posts_data_counter >= 3:
            #     break

            title = data['_source']['title']
            if (title in seen_titles) or (title in new_threads_titles_list):
                continue
            data['_source']['dev_name'] = dev_name
            seen_titles.add(title)
            active_data_list.append(data)
            # active_posts_data_counter += 1
        logger.info(f"No. of active posts collected: {len(active_data_list)}")

    # Determine if there's any update in the data compared to stored JSON
    # Gather titles from stored JSON file
    json_file_path = fr"static/newsletters/newsletter.json"

    current_directory = os.getcwd()
    json_full_path = os.path.join(current_directory, json_file_path)
    stored_json_titles = set()
    if os.path.exists(json_full_path):
        with open(json_full_path, 'r') as j:
            try:
                json_data = json.load(j)
            except Exception as e:
                logger.info(f"Error reading json file:{json_full_path} :: {e}")
                json_data = {}

        stored_json_titles = set(
            [item['title'] for item in json_data.get('new_threads_this_week', [])] +
            [item['title'] for item in json_data.get('active_posts_this_week', [])]
        )
    else:
        logger.warning(f"No existing newsletter.json file found: {json_full_path}")

    # Gather titles from collected Active data and New Threads list
    collected_json_titles = set(
        [data['_source']['title'] for data in active_data_list] +
        [data['_source']['title'] for data in new_threads_list]
    )

    # Generate a new newsletter.json file if changes found in stored JSON file
    if collected_json_titles != stored_json_titles:
        logger.info("Changes found as compared to previously stored JSON file... ")

        delay = 5
        count = 0

        while True:
            try:
                logger.success(f"Total no. of active posts collected: {len(active_data_list)}")
                logger.success(f"Total no. of new threads started this week: {len(new_threads_list)}")

                logger.info("Creating newsletter.json file ... ")
                if len(active_data_list) > 0 or len(new_threads_list) > 0:

                    # Prepare New Threads data for newsletter
                    new_threads_page_data = []
                    new_threads_summary = ""
                    if new_threads_list:
                        new_threads_summary += json_gen.generate_recent_posts_summary(new_threads_list, verbose=True)
                        logger.success(new_threads_summary)

                        for data in tqdm(new_threads_list):
                            try:
                                # Generate all XML files for given title, if not present
                                xml_gen.start(dict_data=[data], url=data['_source']['domain'])
                                entry_data = json_gen.create_single_entry(
                                    data,
                                    base_url_for_xml="https://tldr.bitcoinsearch.xyz/summary",
                                    look_for_combined_summary=True,
                                    remove_xml_extension=True
                                )
                                new_threads_page_data.append(entry_data)
                            except Exception as ex:
                                logger.error(
                                    f"Error occurred for doc id: {data['_source']['id']}\n{ex} \n{traceback.format_exc()}")
                    else:
                        logger.warning(f"No new threads started this week, generating summary of active posts this "
                                       f"week ...")
                        # If no new threads started this week, generate summary from active posts of the given week
                        new_threads_summary += json_gen.generate_recent_posts_summary(active_data_list)
                        logger.success(new_threads_summary)

                    # Prepare active posts data for newsletter
                    active_page_data = []
                    for data in tqdm(active_data_list):
                        try:
                            # Generate all XML files for given title, if not present
                            xml_gen.start(dict_data=[data], url=data['_source']['domain'])
                            entry_data = json_gen.create_single_entry(
                                data, base_url_for_xml="https://tldr.bitcoinsearch.xyz/summary",
                                look_for_combined_summary=True, remove_xml_extension=True
                            )
                            active_page_data.append(entry_data)
                        except Exception as ex:
                            logger.error(
                                f"Error occurred for doc id: {data['_source']['id']}\n{ex} \n{traceback.format_exc()}")

                    # Compile and save data for newsletter file
                    json_string = {
                        "summary_of_threads_started_this_week": new_threads_summary,
                        "new_threads_this_week": new_threads_page_data,
                        "active_posts_this_week": active_page_data
                    }
                    json_gen.write_json_file(json_string, json_file_path)
                    archive_json_file_path = fr"static/newsletters/{str_month_year}/{current_date_str}-newsletter.json"
                    json_gen.store_file_in_archive(json_file_path, archive_json_file_path)
                else:
                    logger.error(f"Data list empty! Please check the data again.")
                break
            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                time.sleep(delay)
                count += 1
                if count > 1:
                    sys.exit(f"{ex}")
    else:
        # If no changes found in stored JSON file, save the previous one with updated name in the archive directory
        logger.success("No change in the posts, no need to update newsletter.json file")
        if os.path.exists(json_full_path):
            archive_json_file_path = fr"static/newsletters/{str_month_year}/{current_date_str}-newsletter.json"
            json_gen.store_file_in_archive(json_file_path, archive_json_file_path)
