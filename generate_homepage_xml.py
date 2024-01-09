import random
import pandas as pd
import time
import traceback
from datetime import datetime, timedelta
from loguru import logger
import os
import sys
import warnings
import json
import shutil

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.json_utils import GenerateJSON
from src.xml_utils import GenerateXML
from src.utils import month_dict

warnings.filterwarnings("ignore")

if __name__ == "__main__":

    gen = GenerateJSON()
    xml_gen = GenerateXML()
    elastic_search = ElasticSearchClient()
    dev_urls = [
        "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/",
        "https://delvingbitcoin.org/"
    ]

    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")

    start_date = datetime.now() - timedelta(days=7)
    start_date_str = start_date.strftime("%Y-%m-%d")
    logger.info(f"start_date: {start_date_str}")
    logger.info(f"current_date_str: {current_date_str}")

    month_name = month_dict[int(current_date.month)]
    str_month_year = f"{month_name}_{int(current_date.year)}"

    json_file_path = fr"static/homepage.json"

    recent_data_list = []
    active_data_list = []
    today_in_history_data_list = []

    random_years_ago = None

    for dev_url in dev_urls:
        logger.info(f"Working on URL: {dev_url}")
        fetch_today_in_history = True

        all_data_df, all_data_list = elastic_search.fetch_all_data_for_url(ES_INDEX, url=dev_url)
        data_list = elastic_search.extract_data_from_es(
            ES_INDEX, dev_url, start_date_str, current_date_str, exclude_combined_summary_docs=True
        )
        dev_name = dev_url.split("/")[-2]
        logger.success(f"TOTAL THREADS RECEIVED FOR - {dev_name}: {len(data_list)}")

        seen_titles = set()

        # top active posts
        active_posts_data = elastic_search.filter_top_active_posts(es_results=data_list, top_n=10,
                                                                   all_data_df=all_data_df)

        active_posts_data_counter = 0
        for data in active_posts_data:
            if active_posts_data_counter >= 3:
                break

            title = data['_source']['title']
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # get the first post's info of this title
            df_title = all_data_df.loc[(all_data_df['title'] == title) & (all_data_df['domain'] == dev_url)]
            df_title.sort_values(by='created_at', inplace=True)
            original_post = df_title.iloc[0].to_dict()

            counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url,
                                                                                 df=df_title)

            for i in all_data_list:
                if i['_source']['title'] == original_post['title'] and i['_source']['domain'] == original_post[
                    'domain'] and i['_source']['authors'] == original_post['authors'] and i['_source']['created_at'] == \
                        original_post['created_at'] and i['_source']['url'] == original_post['url']:
                    for author in i['_source']['authors']:
                        contributors.remove(author)
                    i['_source']['n_threads'] = counts
                    i['_source']['contributors'] = contributors
                    i['_source']['dev_name'] = dev_name
                    active_data_list.append(i)
                    active_posts_data_counter += 1
                    break

        logger.success(f"Number of active posts collected: {len(active_data_list)}, for URL: {dev_url}")

        # top recent posts
        recent_data_post_counter = 0
        recent_posts_data = elastic_search.filter_top_recent_posts(es_results=data_list, top_n=20)
        for data in recent_posts_data:

            # if preprocess body text not longer than token_threshold, skip that post
            if not gen.is_body_text_long(data=data, sent_threshold=2):
                logger.info(f"skipping: {data['_source']['title']} - {data['_source']['url']}")
                continue

            title = data['_source']['title']
            if title in seen_titles:
                continue
            seen_titles.add(title)
            if recent_data_post_counter >= 3:
                break
            counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url,
                                                                                 df=all_data_df)
            authors = data['_source']['authors']
            for author in authors:
                contributors.remove(author)
            data['_source']['n_threads'] = counts
            data['_source']['contributors'] = contributors
            data['_source']['dev_name'] = dev_name
            recent_data_list.append(data)
            recent_data_post_counter += 1

        if not recent_data_list:
            for data in recent_posts_data:
                # if preprocess body text not longer than token_threshold, skip that post
                if not gen.is_body_text_long(data=data, sent_threshold=2):
                    logger.info(f"skipping: {data['_source']['title']} - {data['_source']['url']}")
                    continue

                title = data['_source']['title']
                # if title in seen_titles:
                #     continue
                seen_titles.add(title)
                if recent_data_post_counter >= 3:
                    break
                counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url,
                                                                                     df=all_data_df)
                authors = data['_source']['authors']
                for author in authors:
                    contributors.remove(author)
                data['_source']['n_threads'] = counts
                data['_source']['contributors'] = contributors
                data['_source']['dev_name'] = dev_name
                recent_data_list.append(data)
                recent_data_post_counter += 1

        logger.success(f"Number of recent posts collected: {len(recent_data_list)}, for URL: {dev_url}")

        # today in history posts
        logger.info(f"fetching 'Today in history' posts... ")

        if not random_years_ago:
            at_least_years_ago = 3
            at_max_years_ago = current_date.year - 2015
            random_years_ago = random.randint(at_least_years_ago, at_max_years_ago)
            logger.info(f"random years ago between {at_least_years_ago} to {at_max_years_ago}: {random_years_ago}")

        if dev_url == "https://delvingbitcoin.org/":
            random_years_ago = random.randint(1, current_date.year - 2022)
            logger.info(f"for delving-bitcoin - random years ago between {1} to {current_date.year - 2022}: {random_years_ago}")

        default_days_to_look_back = 6
        loop_counter = 1
        docs_counter = 0

        while fetch_today_in_history:
            days_to_look_back = default_days_to_look_back * loop_counter
            selected_random_date = current_date - timedelta(days=365 * random_years_ago)
            start_of_time = selected_random_date - timedelta(days=selected_random_date.weekday())
            end_of_time = start_of_time + timedelta(days=days_to_look_back)
            logger.info(f"collecting the data for {days_to_look_back} days ... ::: Start of week: {start_of_time}, "
                        f"End of week: {end_of_time}")

            all_data_df['created_at'] = pd.to_datetime(all_data_df['created_at'], errors='coerce')
            all_data_df['created_at_'] = all_data_df['created_at'].dt.tz_convert(None)
            df_selected_threads = all_data_df.loc[(all_data_df['created_at_'] >= start_of_time) &
                                                  (all_data_df['created_at_'] <= end_of_time)]
            logger.info(f"Shape of df_selected_threads: {df_selected_threads.shape}")

            if len(df_selected_threads) > 0:
                for idx, row in df_selected_threads.iterrows():
                    this_title = row['title']
                    this_created_at = row['created_at'].to_pydatetime().replace(tzinfo=None)
                    this_type = row['type']

                    if this_type == 'original_post':
                        logger.info(f"collecting an original thread created at {this_created_at}")
                        df_title = all_data_df.loc[
                            (all_data_df['title'] == this_title) & (all_data_df['domain'] == dev_url)]
                        df_title.sort_values(by='created_at', inplace=True)
                        logger.info(f"No. of posts found for title: '{this_title}' ::: {df_title.shape}")

                        counts, contributors = elastic_search.fetch_contributors_and_threads(title=this_title,
                                                                                             domain=dev_url,
                                                                                             df=df_title)
                        if counts < 5:
                            logger.info(f"No. of replies are less than 5, skipping it... ")
                            continue

                        for d in all_data_list:
                            if d['_source']['title'] == this_title and d['_source']['domain'] == row['domain'] and \
                                    d['_source']['authors'] == row['authors'] and d['_source']['url'] == row['url']:
                                if contributors:
                                    for author in d['_source']['authors']:
                                        contributors.remove(author)
                                d['_source']['n_threads'] = counts
                                d['_source']['contributors'] = contributors
                                d['_source']['dev_name'] = dev_name
                                today_in_history_data_list.append(d)
                                fetch_today_in_history = False
                                break
            loop_counter += 1

        # add history data from yesterday's homepage.json
        if not today_in_history_data_list:
            logger.info("Collecting yesterday's history threads!")
            current_directory = os.getcwd()
            full_path = os.path.join(current_directory, json_file_path)
            if os.path.exists(full_path):
                with open(full_path, 'r') as j:
                    data = json.load(j)
                    today_in_history_data_list.extend(data['today_in_history_posts'])

        logger.success(f"No. of 'Today in history' posts collected: {len(today_in_history_data_list)}")

    xml_ids = gen.get_existing_json_title(file_path=json_file_path)
    recent_post_ids = [data['_source']['title'] for data in recent_data_list]
    active_post_ids = [data['_source']['title'] for data in active_data_list]

    # Combine the titles to create a concatenated set
    all_post_titles = set(recent_post_ids + active_post_ids)

    if all_post_titles != set(xml_ids):
        logger.info("changes found in recent posts ... ")

        delay = 5
        count = 0

        while True:
            try:
                logger.info(
                    f"active posts: {len(active_data_list)}, "
                    f"recent posts: {len(recent_data_list)}, "
                    f"today in history posts: {len(today_in_history_data_list)}"
                )
                logger.info("Creating homepage.json file ... ")

                # header summary
                if len(active_data_list) > 0 or len(recent_data_list) > 0:
                    recent_post_summ = gen.generate_recent_posts_summary(recent_data_list)
                    logger.success(recent_post_summ)

                    # recent data
                    recent_page_data = []
                    for data in recent_data_list:

                        # check if individual and combined xml file exists
                        individual_file_exist, combined_file_exist = gen.check_local_xml_files_exists(
                            data, look_for_combined_summary_file=True
                        )

                        if not individual_file_exist:
                            this_doc_id = data['_source']['id']
                            logger.info(f"individual summary file does not exist for id: {this_doc_id}")

                            this_doc_data = elastic_search.fetch_data_based_on_id(es_index=ES_INDEX,
                                                                                  id_str=this_doc_id)
                            logger.info(f"Total docs found: {len(this_doc_data)}")

                            xml_gen.start(dict_data=this_doc_data, url=data['_source']['domain'])
                            logger.info(f"xml generation complete")

                        entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                        recent_page_data.append(entry_data)

                    # active data
                    active_page_data = []
                    for data in active_data_list:

                        # check if individual and combined xml file exists
                        individual_file_exist, combined_file_exist = gen.check_local_xml_files_exists(
                            data, look_for_combined_summary_file=True
                        )

                        if not individual_file_exist:
                            this_doc_id = data['_source']['id']
                            logger.info(f"individual summary file does not exist for id: {this_doc_id}")

                            this_doc_data = elastic_search.fetch_data_based_on_id(es_index=ES_INDEX,
                                                                                  id_str=this_doc_id)
                            logger.info(f"Total docs found: {len(this_doc_data)}")

                            xml_gen.start(dict_data=this_doc_data, url=data['_source']['domain'])
                            logger.info(f"xml generation complete")

                        entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                        active_page_data.append(entry_data)

                    # today in history
                    today_in_history_data = []
                    collected_dev_data = []
                    if len(today_in_history_data_list) > 0:
                        for data in today_in_history_data_list:

                            # check if individual and combined xml file exists
                            individual_file_exist, combined_file_exist = gen.check_local_xml_files_exists(
                                data, look_for_combined_summary_file=True
                            )

                            if not individual_file_exist:
                                this_doc_id = data['_source']['id']
                                logger.info(f"individual summary file does not exist for id: {this_doc_id}")

                                this_doc_data = elastic_search.fetch_data_based_on_id(es_index=ES_INDEX,
                                                                                      id_str=this_doc_id)
                                logger.info(f"Total docs found: {len(this_doc_data)}")

                                xml_gen.start(dict_data=this_doc_data, url=data['_source']['domain'])
                                logger.info(f"xml generation complete")

                            entry_data = gen.create_single_entry(data, look_for_combined_summary=True,
                                                                 add_combined_summary_field=True)
                            if entry_data['dev_name'] not in collected_dev_data:
                                collected_dev_data.append(entry_data['dev_name'])
                                logger.info(f"collected data for: {collected_dev_data}")
                                today_in_history_data.append(entry_data)

                    json_string = {
                        "header_summary": recent_post_summ,
                        "recent_posts": recent_page_data,
                        "active_posts": active_page_data,
                        "today_in_history_posts": today_in_history_data
                    }

                    with open(json_file_path, 'w') as f:
                        f.write(json.dumps(json_string, indent=4))
                        logger.success(f"saved file: {json_file_path}")

                    archive_json_file_path = fr"static/homepage/{str_month_year}/{current_date_str}-homepage.json"
                    archive_dirname = os.path.dirname(archive_json_file_path)
                    os.makedirs(archive_dirname, exist_ok=True)
                    shutil.copy(json_file_path, archive_json_file_path)
                    logger.success(f'archive updated with file: {archive_json_file_path}')
                else:
                    logger.error(f"Data list empty! Please check the data again.")
                break

            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                time.sleep(delay)
                count += 1
                if count > 3:
                    sys.exit(f"{ex}")
    else:
        logger.success("No change in recent posts, no need to update homepage.json file")
