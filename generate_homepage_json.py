import json
import os
import random
import sys
import time
import traceback
import warnings
from datetime import datetime, timedelta

from loguru import logger
from tqdm import tqdm

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.json_utils import GenerateJSON
from src.utils import month_dict
from src.xml_utils import GenerateXML

warnings.filterwarnings("ignore")


def page_data_handling(data_list: list, get_unique_per_dev=False):
    """
    Handle the page data by generating XML files and creating single entries.

    Args:
        data_list (list): A list of dictionaries containing page data.
        get_unique_per_dev (bool, optional): Flag indicating whether to get only unique documents per development domain. Defaults to False.

    Returns:
        list: A list of dictionaries containing processed page data.
    """
    page_data = []
    collected_dev_data = []
    for data in tqdm(data_list):
        try:
            # Generate all XML files for each given title, if not present
            xml_gen.start(dict_data=[data], url=data['_source']['domain'])
            entry_data = json_gen.create_single_entry(data, look_for_combined_summary=True)
            if get_unique_per_dev:  # Ensure that there is only one document per domain
                if entry_data['dev_name'] not in collected_dev_data:
                    collected_dev_data.append(entry_data['dev_name'])
                    logger.info(f"collected data for: {collected_dev_data}")
                    page_data.append(entry_data)
            else:
                page_data.append(entry_data)
        except Exception as ex:
            logger.error(
                f"Error occurred for doc id: {data['_source']['id']}\n{ex} \n{traceback.format_exc()}")
    return page_data


if __name__ == "__main__":

    json_gen = GenerateJSON()
    xml_gen = GenerateXML()
    elastic_search = ElasticSearchClient()

    dev_urls = [
        ["https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
         "https://gnusha.org/pi/bitcoindev/"],
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/",
        "https://delvingbitcoin.org/"
    ]

    # Set the date range for data extraction
    current_date = datetime.now()
    start_date = current_date - timedelta(days=7)

    start_date_str = start_date.strftime("%Y-%m-%d")
    current_date_str = current_date.strftime("%Y-%m-%d")

    logger.info(f"start_date: {start_date_str}")
    logger.info(f"current_date_str: {current_date_str}")

    # Convert month from number to name for filename construction
    month_name = month_dict[int(current_date.month)]
    str_month_year = f"{month_name}_{int(current_date.year)}"

    recent_data_list = []
    active_data_list = []
    today_in_history_data_list = []
    history_data_collected_from_yesterday = False
    random_years_ago = None

    # path to the stored homepage.json file
    json_file_path = fr"static/homepage.json"

    # Process each URL in the dev_urls list
    for dev_url in dev_urls:
        logger.info(f"Working on URL: {dev_url}")
        fetch_today_in_history = True

        # Fetch docs from an elasticsearch index
        data_list = elastic_search.extract_data_from_es(
            ES_INDEX, dev_url, start_date_str, current_date_str, exclude_combined_summary_docs=True
        )

        dev_name = dev_url[0].split("/")[-2] if isinstance(dev_url, list) else dev_url.split("/")[-2]
        logger.success(f"Retrieved {len(data_list)} threads for {dev_name}")

        seen_titles = set()

        # TOP ACTIVE POSTS
        active_posts_data = elastic_search.filter_top_active_posts(
            es_results=data_list, top_n=10
        )

        # Collect N active posts per domain
        active_posts_data_counter = 0
        for data in active_posts_data:
            if active_posts_data_counter >= 3:
                break

            title = data['_source']['title']
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # Fetch the first post for given title and domain
            original_post = elastic_search.get_earliest_posts_by_title(
                es_index=ES_INDEX, url=dev_url, title=title
            )

            # Gather post counts for given title and its total contributors
            counts, contributors = elastic_search.es_fetch_contributors_and_threads(
                es_index=ES_INDEX, title=title, domain=dev_url
            )

            # As we want to show the original/first post of the filtered active post,
            # we are parsing information from 'original_post',
            # otherwise we would parse the information from 'data' if we want to show the filtered post itself

            # Separate out an original author from contributor's list
            for author in original_post['_source']['authors']:
                contributors.remove(author)
            original_post['_source']['n_threads'] = counts
            original_post['_source']['contributors'] = contributors
            original_post['_source']['dev_name'] = dev_name
            active_data_list.append(original_post)
            active_posts_data_counter += 1

        logger.success(f"Number of active posts collected: {len(active_data_list)}, for URL: {dev_url}")

        # TOP RECENT POSTS
        recent_data_post_counter = 0
        recent_posts_data = elastic_search.filter_top_recent_posts(es_results=data_list, top_n=20)

        for data in recent_posts_data:
            # If preprocessed body text shorter than token_threshold, skip the doc
            if not json_gen.is_body_text_long(data=data, sent_threshold=2):
                logger.info(f"skipping: {data['_source']['title']} - {data['_source']['url']}")
                continue

            title = data['_source']['title']
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # Collect N recent posts per domain
            if recent_data_post_counter >= 3:
                break

            # Gather post counts for given title and its total contributors
            counts, contributors = elastic_search.es_fetch_contributors_and_threads(
                es_index=ES_INDEX, title=title, domain=dev_url
            )

            # Separate out an original author from contributor's list
            for author in data['_source']['authors']:
                contributors.remove(author)
            data['_source']['n_threads'] = counts
            data['_source']['contributors'] = contributors
            data['_source']['dev_name'] = dev_name
            recent_data_list.append(data)
            recent_data_post_counter += 1

        if not recent_data_list:
            for data in recent_posts_data:
                # If the preprocessed body text shorter than token_threshold, skip that post
                if not json_gen.is_body_text_long(data=data, sent_threshold=2):
                    logger.info(f"skipping: {data['_source']['title']} - {data['_source']['url']}")
                    continue

                title = data['_source']['title']
                # Collect N recent posts per domain
                if recent_data_post_counter >= 3:
                    break
                counts, contributors = elastic_search.es_fetch_contributors_and_threads(
                    es_index=ES_INDEX, title=title, domain=dev_url
                )

                # Separate out an original author from contributor's list
                for author in data['_source']['authors']:
                    contributors.remove(author)
                data['_source']['n_threads'] = counts
                data['_source']['contributors'] = contributors
                data['_source']['dev_name'] = dev_name
                recent_data_list.append(data)
                recent_data_post_counter += 1

        logger.success(f"Number of recent posts collected: {len(recent_data_list)}, for URL: {dev_url}")

        # TODAY IN HISTORY POSTS
        logger.info(f"fetching 'Today in history' posts... ")

        # Randomly choose a number N within given range and look back N for the data N years ago
        # for bitcoin-dev and lighting-dev we have data from 2015, and for delving-bitcoin we have it from 2022
        if not random_years_ago:
            at_least_years_ago = 3
            at_max_years_ago = current_date.year - 2015
            random_years_ago = random.randint(at_least_years_ago, at_max_years_ago)
            logger.info(f"Random years ago between {at_least_years_ago} to {at_max_years_ago}: {random_years_ago}")

        if dev_url == "https://delvingbitcoin.org/":
            random_years_ago = random.randint(1, current_date.year - 2022)
            logger.info(
                f"for delving-bitcoin - random years ago between {1} to {current_date.year - 2022}: {random_years_ago}")

        default_days_to_look_back = 6
        loop_counter = 1

        while fetch_today_in_history:
            days_to_look_back = default_days_to_look_back * loop_counter
            selected_random_date = current_date - timedelta(days=365 * random_years_ago)

            start_of_time = selected_random_date - timedelta(days=selected_random_date.weekday())
            end_of_time = start_of_time + timedelta(days=days_to_look_back)

            start_of_time_str = start_of_time.strftime("%Y-%m-%dT%H:%M:%S")
            end_of_time_str = end_of_time.strftime("%Y-%m-%dT%H:%M:%S")

            logger.info(
                f"collecting the data from {days_to_look_back} days range ... || Start of week: {start_of_time} | "
                f"End of week: {end_of_time}")

            selected_threads = elastic_search.fetch_data_in_date_range(
                es_index=ES_INDEX,
                start_date=start_of_time_str,
                end_date=end_of_time_str,
                domain=dev_url
            )

            if len(selected_threads) > 0:
                for doc in selected_threads:
                    doc_title = doc['_source']['title']
                    doc_created_at = doc['_source']['created_at']

                    if doc['_source']['type'] == 'original_post':

                        counts, contributors = elastic_search.es_fetch_contributors_and_threads(
                            es_index=ES_INDEX, title=doc_title, domain=dev_url
                        )

                        if counts < 5:
                            logger.info(f"No. of replies are less than 5, skipping it... ")
                            continue

                        if contributors:
                            # Separate out an original author from contributor's list
                            for author in doc['_source']['authors']:
                                contributors.remove(author)
                        doc['_source']['n_threads'] = counts
                        doc['_source']['contributors'] = contributors
                        doc['_source']['dev_name'] = dev_name
                        today_in_history_data_list.append(doc)
                        logger.info(f"collected doc created on: {doc_created_at} || TITLE: {doc_title}")
                        fetch_today_in_history = False
                        break
            loop_counter += 1

        # If not data found for given time period, collect the history data from stored homepage.json file
        if not today_in_history_data_list:
            logger.info("Collecting yesterday's history threads!")
            current_directory = os.getcwd()
            full_path = os.path.join(current_directory, json_file_path)
            if os.path.exists(full_path):
                with open(full_path, 'r') as j:
                    try:
                        data = json.load(j)
                    except Exception as e:
                        logger.info(f"Error reading json file:{full_path} :: {e}")
                        data = {}
                    today_in_history_data_list.extend(data.get('today_in_history_posts', []))
                    history_data_collected_from_yesterday = True

        logger.success(f"No. of 'Today in history' posts collected: {len(today_in_history_data_list)}")

    # Determine if there's any update in the data as compared to stored JSON file
    current_directory = os.getcwd()
    full_path = os.path.join(current_directory, json_file_path)
    if os.path.exists(full_path):
        with open(full_path, 'r') as j:
            try:
                yesterday_data = json.load(j)
            except Exception as e:
                logger.info(f"Error reading json file:{full_path} :: {e}")
                yesterday_data = {}

    stored_json_titles = json_gen.get_existing_json_title(file_path=json_file_path)
    collected_post_titles = set([data['_source']['title'] for data in recent_data_list] +
                                [data['_source']['title'] for data in active_data_list])

    if collected_post_titles != set(stored_json_titles):
        logger.info("Changes found as compared to previously stored JSON file... ")

        delay = 5
        count = 0

        while True:
            try:
                logger.info(
                    f"Active posts: {len(active_data_list)}, "
                    f"Recent posts: {len(recent_data_list)}, "
                    f"Today in history posts: {len(today_in_history_data_list)}"
                )
                logger.info("Creating homepage.json file ... ")

                recent_post_summ = ""
                if len(active_data_list) > 0 or len(recent_data_list) > 0:

                    # Generate the header summary from recent posts,
                    # and if no recent data is collected then from active posts
                    if len(recent_data_list) > 0:
                        recent_post_summ = json_gen.generate_recent_posts_summary(recent_data_list)
                    else:
                        recent_post_summ = json_gen.generate_recent_posts_summary(active_data_list)
                    logger.success(recent_post_summ)

                    # Compile recent posts data
                    recent_page_data = page_data_handling(recent_data_list)

                    # Compile active posts data
                    active_page_data = page_data_handling(active_data_list)

                else:
                    logger.error(f"'Active' and 'Recent' data list empty! Please check the data again.")
                    recent_page_data, active_page_data = [], []

                # Compile today in history posts
                if history_data_collected_from_yesterday:
                    logger.info("No change in 'Today in History' data posts, gathering data from yesterday's post.")
                    today_in_history_data = yesterday_data.get('today_in_history_posts', [])
                else:
                    if len(today_in_history_data_list) > 0:
                        today_in_history_data = page_data_handling(today_in_history_data_list, get_unique_per_dev=True)
                    else:
                        logger.error(f"'Today in history' data list empty! Please check the data again.")
                        today_in_history_data = []

                json_string = {
                    "header_summary": recent_post_summ,
                    "recent_posts": recent_page_data,
                    "active_posts": active_page_data,
                    "today_in_history_posts": today_in_history_data
                }
                json_gen.write_json_file(json_string, json_file_path)

                archive_json_file_path = fr"static/homepage/{str_month_year}/{current_date_str}-homepage.json"
                json_gen.store_file_in_archive(json_file_path, archive_json_file_path)
                break

            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                time.sleep(delay)
                count += 1
                if count > 1:
                    sys.exit(f"{ex}")
    else:
        # If no changes found in Recent or Active posts,
        # simply gather all data from yesterday's stored json file and save it with an updated name in the archive directory
        logger.info("No change in 'Recent' or 'Active' posts.")
        rewrite_json_file = False

        if history_data_collected_from_yesterday:
            logger.info("No change in 'Today in History' data posts, gathering data from yesterday's post.")
            today_in_history_data = yesterday_data.get('today_in_history_posts', [])
        else:
            rewrite_json_file = True
            if len(today_in_history_data_list) > 0:
                today_in_history_data = page_data_handling(today_in_history_data_list, get_unique_per_dev=True)
            else:
                logger.error(f"'Today in history' data list empty! Please check the data again.")
                today_in_history_data = []

        if rewrite_json_file:
            logger.info(f'Rewriting the homepage.json file')
            json_string = {
                "header_summary": yesterday_data.get('header_summary', []),
                "recent_posts": yesterday_data.get('recent_posts', []),
                "active_posts": yesterday_data.get('recent_posts', []),
                "today_in_history_posts": today_in_history_data
            }
            json_gen.write_json_file(json_string, json_file_path)
        else:
            logger.info("No need to rewrite homepage.json file")

        if os.path.exists(full_path):
            archive_json_file_path = fr"static/homepage/{str_month_year}/{current_date_str}-homepage.json"
            json_gen.store_file_in_archive(json_file_path, archive_json_file_path)
