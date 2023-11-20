import re
import pandas as pd
from elasticsearch import Elasticsearch
import time
import traceback
import openai
from datetime import datetime, timedelta
from loguru import logger
import xml.etree.ElementTree as ET
import os
from dotenv import load_dotenv
import sys
import warnings
import pytz
import json
import numpy as np
import nltk

nltk.download('punkt')
from nltk.tokenize import sent_tokenize

from src.utils import preprocess_email
from src.gpt_utils import generate_chatgpt_summary, consolidate_chatgpt_summary
from src.config import TOKENIZER, ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE, \
    CHAT_COMPLETION_MODEL

warnings.filterwarnings("ignore")
load_dotenv()

OPENAI_ORG_KEY = os.getenv("OPENAI_ORG_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.organization = OPENAI_ORG_KEY
openai.api_key = OPENAI_API_KEY


class ElasticSearchClient:
    def __init__(self, es_cloud_id, es_username, es_password, es_data_fetch_size=ES_DATA_FETCH_SIZE) -> None:
        self._es_cloud_id = es_cloud_id
        self._es_username = es_username
        self._es_password = es_password
        self._es_data_fetch_size = es_data_fetch_size
        self._es_client = Elasticsearch(
            cloud_id=self._es_cloud_id,
            http_auth=(self._es_username, self._es_password),
        )

    def extract_data_from_es(self, es_index, url, start_date_str, current_date_str):
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "prefix": {  # Using prefix query for domain matching
                                    "domain.keyword": str(url)
                                }
                            },
                            {
                                "range": {
                                    "created_at": {
                                        "gte": f"{start_date_str}T00:00:00.000Z",
                                        "lte": f"{current_date_str}T23:59:59.999Z"
                                    }
                                }
                            }
                        ]
                    }
                }
            }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            # output_data_path = f'{data_path}/{es_index}.json'
            # with open(output_data_path, 'w') as f:
            while len(results) > 0:
                # Save the current batch of results
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def filter_top_recent_posts(self, es_results, top_n):
        es_results_sorted = sorted(
            es_results,
            key=lambda x: datetime.strptime(x['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ'), reverse=True
        )
        unique_results = []
        seen_titles = set()

        # Iterate through the sorted results
        for result in es_results_sorted:
            title = result['_source']['title']
            # Only add the result if we haven't already seen the title
            if title not in seen_titles:
                unique_results.append(result)
                seen_titles.add(title)

            # Break after we've gotten top_n unique results
            if len(unique_results) >= top_n:
                break

        return unique_results

    def filter_top_active_posts(self, es_results, top_n, all_data_df):
        unique_results = []
        seen_titles = set()

        thread_dict = {}

        # Add this loop to create dictionary with title as key and thread count as value
        for result in es_results:
            title = result['_source']['title']
            if title not in seen_titles:
                counts, contributors = self.fetch_contributors_and_threads(title=title,
                                                                           domain=result['_source']['domain'],
                                                                           df=all_data_df)
                thread_dict[title] = counts  # add counts as value to thread_dict with key as title
                result['_source']['n_threads'] = counts  # add thread count to source
                seen_titles.add(title)

        # Use the dictionary created above, to sort the results
        es_results_sorted = sorted(
            es_results,
            key=lambda x: thread_dict[x['_source']['title']], reverse=True
        )

        seen_titles = set()
        for result in es_results_sorted:
            title = result['_source']['title']
            if title not in seen_titles:
                unique_results.append(result)
                seen_titles.add(title)

            # Break after we've gotten top_n unique results
            if len(unique_results) >= top_n:
                break

        return unique_results

    def fetch_all_data_for_url(self, es_index, url, start_date_str=None, end_date_str=None):
        logger.info(f"fetching all the data")
        output_list = []
        raw_output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.info("connected to the ElasticSearch")
            if start_date_str and end_date_str:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "prefix": {
                                        "domain.keyword": str(url)
                                    }
                                },
                                {
                                    "range": {
                                        "created_at": {
                                            "gte": f"{start_date_str}T00:00:00.000Z",
                                            "lte": f"{end_date_str}T23:59:59.999Z"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            else:
                query = {
                    "query": {
                        "match_phrase": {
                            "domain.keyword": str(url)
                        }
                    }
                }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                # Save the current batch of results
                for result in results:
                    raw_output_list.append(result)
                    output_list.append(result['_source'])

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            df = pd.DataFrame(output_list)
            logger.info(f"Total threads received for: {df.shape[0]}")
            return df, raw_output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def fetch_contributors_and_threads(self, title, domain, df):
        df_filtered = df.loc[(df['title'] == title) & (df['domain'] == domain)]
        # df_filtered = df_filtered.drop_duplicates()  # id
        counts = len(df_filtered)
        df_filtered['authors'] = df_filtered['authors'].apply(tuple)
        contributors = df_filtered['authors'].tolist()
        contributors = [i[0] for i in contributors]
        contributors = list(np.unique(contributors))
        return counts, contributors


class GenerateJSON:
    def __init__(self) -> None:
        self.month_dict = {
            1: "Jan", 2: "Feb", 3: "March", 4: "April", 5: "May", 6: "June",
            7: "July", 8: "Aug", 9: "Sept", 10: "Oct", 11: "Nov", 12: "Dec"
        }

    def split_prompt_into_chunks(self, prompt, chunk_size):
        tokens = TOKENIZER.encode(prompt)
        chunks = []

        while len(tokens) > 0:
            current_chunk = TOKENIZER.decode(tokens[:chunk_size]).strip()

            if current_chunk:
                chunks.append(current_chunk)

            tokens = tokens[chunk_size:]

        return chunks

    def get_summary_chunks(self, body, tokens_per_sub_body):
        chunks = self.split_prompt_into_chunks(body, tokens_per_sub_body)
        summaries = []

        logger.info(f"Total chunks: {len(chunks)}")

        for chunk in chunks:
            count = 0
            while True:
                try:
                    time.sleep(2)
                    summary = generate_chatgpt_summary(chunk)
                    summaries.append(summary)
                    break
                except Exception as ex:
                    count += 1
                    if count > 5:
                        sys.exit(f"Chunk summary ran into error: {traceback.format_exc()}")
        return summaries

    def recursive_summary(self, body, tokens_per_sub_body, max_length):
        summaries = self.get_summary_chunks(body, tokens_per_sub_body)

        summary_length = sum([len(TOKENIZER.encode(s)) for s in summaries])

        logger.info(f"Summary length: {summary_length}")
        logger.info(f"Max length: {max_length}")

        if summary_length > max_length:
            logger.info("entering in recursion")
            return self.recursive_summary("".join(summaries), tokens_per_sub_body, max_length)
        else:
            return summaries

    def gpt_api(self, body):
        body_length_limit = 2800
        tokens_per_sub_body = 2700
        summaries = self.recursive_summary(body, tokens_per_sub_body, body_length_limit)

        if len(summaries) > 1:
            logger.info("generating consolidate summary...")
            summary_str = "\n".join(summaries)
            count = 0
            while True:
                try:
                    time.sleep(2)
                    consolidated_summaries = consolidate_chatgpt_summary(summary_str)
                    break
                except Exception as ex:
                    count += 1
                    if count > 5:
                        sys.exit(f"Chunk summary ran into error: {traceback.format_exc()}")

            return consolidated_summaries

        else:
            logger.info("generating individual summary...")
            return "\n".join(summaries)

    def create_summary(self, body):
        summ = self.gpt_api(body)
        return summ

    def clean_title(self, xml_name):
        special_characters = ['/', ':', '@', '#', '$', '*', '&', '<', '>', '\\', '?']
        xml_name = re.sub(r'[^A-Za-z0-9]+', '-', xml_name)
        for sc in special_characters:
            xml_name = xml_name.replace(sc, "-")
        return xml_name

    def get_id(self, id):
        return str(id).split("-")[-1]

    def create_n_bullets(self, body_summary, n=3):
        bullets_prompt = f"""Summarize the following email into {n} distinct sentences based on the guidelines 
        mentioned below. 
            1. Each sentence you write should not exceed fifteen words. 
            2. Each sentence should begin on a new line and should start with a hyphen (-) and you must add space after hyphen (-).
                E.g., - This is a first sentence. - This is a second sentence. - This is a third sentence.
                E.g., Incorrect: "-This is a sentence.-This is another sentence."
                    Correct: "- This is a sentence. - This is another sentence."
            3. Please adhere to all English grammatical rules while writing the sentences, 
                maintaining formal tone and employing proper spacing. 
            4. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
                Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..."
        CONTEXT:\n\n{body_summary}"""

        response = openai.ChatCompletion.create(
            model=CHAT_COMPLETION_MODEL,
            messages=[
                {"role": "system", "content": "You are an intelligent assistant."},
                {"role": "user", "content": f"{bullets_prompt}"},
            ],
            temperature=1,
            max_tokens=300,
        )
        response_str = response['choices'][0]['message']['content'].replace("\n", "").strip()
        response_str = response_str.replace('.- ', '.\n- ')
        response_str = response_str.replace('. - ', '.\n- ')
        return response_str

    def get_xml_summary(self, data):
        number = self.get_id(data["_source"]["id"])
        title = data["_source"]["title"]
        xml_name = self.clean_title(title)
        published_at = datetime.strptime(data['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        published_at = pytz.UTC.localize(published_at)
        month_name = self.month_dict[int(published_at.month)]
        str_month_year = f"{month_name}_{int(published_at.year)}"
        dev_name = data['_source']['dev_name']

        current_directory = os.getcwd()
        file_path = f"static/{dev_name}/{str_month_year}/{number}_{xml_name}.xml"
        full_path = os.path.join(current_directory, file_path)

        if os.path.exists(full_path):
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(full_path)
            root = tree.getroot()
            summ_list = root.findall(".//atom:entry/atom:summary", namespaces)
            summ = "\n".join([summ.text for summ in summ_list])
            author_list = root.findall(".//atom:author", namespaces)
            author_ = "\n".join([a.find('atom:name', namespaces).text for a in author_list])
            author_ = " ".join(author_.split(" ")[:-2])
            return f"{author_}:{summ}\n"
        else:
            logger.warning(f"No xml file found: {full_path}")
            return ""

    def generate_recent_posts_summary(self, dict_list):
        logger.info("working on given post's summary")

        recent_post_data = ""

        for data in dict_list:
            xml_summ = self.get_xml_summary(data)
            recent_post_data += xml_summ

            if xml_summ is None:
                body = data['_source']['body']
                author_ = data['_source']['authors']
                author_ = ", ".join([a for a in author_])
                body = preprocess_email(body)
                body_summ = self.create_summary(body)
                summ = f"{author_}:{body_summ}\n"
                recent_post_data += summ
        recent_post_data = self.create_summary(recent_post_data)

        summ_prompt = f"""You are required to produce a concise header summary from a compilation of condensed recent discussions. Transform the following extracted text from mailing lists into a brief summary composed of only three or four significant sentences, adhering to these important criteria:
    Guidelines:
        1. While synthesizing, refrain from or reword phrases like "The context discusses...", "The email discusses...", "In this context...", "The context covers...", "The context questions...", "In this email...", "The email covers..." and similar phrases.
        2. The summarization must have a formal tone and be high in informational content.
        3. Ensure that punctuation is followed by a space and that all syntax rules are adhered to.
        4. Any links given within the text should be retained and appropriately incorporated.
        5. Rather than being a simple rewording of the original content, the summary should restructure and simplify the main points.
        6. Mention full names (both the first name and last name) of the authors if applicable. 
        7. Break down the summary into concise, meaningful paragraphs ensuring each paragraph captures a unique aspect or perspective from the original text, provided it should be no longer than three or four sentences.
        8. Please ensure that the summary does not start with labels like "Email 1:", "Email 2:" and so on.
        \n CONTEXT:\n\n{recent_post_data}"""

        response = openai.ChatCompletion.create(
            model=CHAT_COMPLETION_MODEL,
            messages=[
                {"role": "system", "content": "You are an intelligent agent with an exceptional skills in writing."},
                {"role": "user", "content": f"{summ_prompt}"},
            ],
            temperature=0.7,
            max_tokens=500
        )
        response_str = response['choices'][0]['message']['content'].strip()
        if response_str.startswith("Summary:"):
            response_str = response_str[8:].strip()
        return response_str

    def create_single_entry(self, data, base_url_for_xml="static", look_for_combined_summary=False,
                            remove_xml_extension=False):
        number = self.get_id(data["_source"]["id"])
        title = data["_source"]["title"]
        published_at = datetime.strptime(data['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        published_at = pytz.UTC.localize(published_at)
        contributors = data['_source']['contributors']
        url = data['_source']['url']
        authors = data['_source']['authors']
        body = data['_source']['body']
        local_dev_name = data['_source']['dev_name']
        xml_name = self.clean_title(title)
        month_name = self.month_dict[int(published_at.month)]
        str_month_year = f"{month_name}_{int(published_at.year)}"

        combined_summ_file_path = ""
        base_path = f"{base_url_for_xml}/{local_dev_name}/{str_month_year}"
        file_extension = "" if remove_xml_extension else ".xml"
        if look_for_combined_summary:
            if os.path.exists(f"static/{local_dev_name}/{str_month_year}/combined_{xml_name}.xml"):
                combined_summ_file_path = f"{base_path}/combined_{xml_name}{file_extension}"
            else:
                combined_summ_file_path = ""
        file_path = f"{base_path}/{number}_{xml_name}{file_extension}"

        # fetch the summary from xml if exist
        xml_summary = self.get_xml_summary(data)

        if xml_summary is None:
            xml_summary = self.create_summary(body)

        bullets = self.create_n_bullets(xml_summary, n=3)

        entry_data = {
            "id": number,
            "title": title,
            "link": url,
            "authors": authors,
            "published_at": published_at.isoformat(),
            "summary": bullets,
            "n_threads": data["_source"]["n_threads"],
            "dev_name": local_dev_name,
            "contributors": contributors,
            "file_path": file_path,
            "combined_summ_file_path": combined_summ_file_path
        }
        return entry_data

    def create_json_feed(self, recent_dict_list, active_data_list, file_name="homepage.json"):
        recent_post_summ = self.generate_recent_posts_summary(recent_dict_list)

        logger.success(recent_post_summ)

        json_string = {"header_summary": recent_post_summ}

        recent_page_data = []
        for data in recent_dict_list:
            entry_data = self.create_single_entry(data)
            recent_page_data.append(entry_data)

        json_string["recent_posts"] = recent_page_data

        active_page_data = []
        for data in active_data_list:
            entry_data = self.create_single_entry(data, look_for_combined_summary=True)
            active_page_data.append(entry_data)

        json_string["active_posts"] = active_page_data

        f_name = f"static/{file_name}"
        with open(f_name, 'w') as f:
            f.write(json.dumps(json_string, indent=4))
            logger.success(f"saved file: {f_name}")
        return f_name

    def start_process(self, data_list_1, data_list_2):
        logger.info("Creating homepage.json file ... ")
        if len(data_list_1) > 0 or len(data_list_2) > 0:
            _ = self.create_json_feed(data_list_1, data_list_2)
        else:
            logger.error(f"Data list empty! Please check the data again.")

    def get_existing_json_ids(self, file_path):
        current_directory = os.getcwd()
        full_path = os.path.join(current_directory, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r') as j:
                data = json.load(j)
            id_list = [item['title'] for item in data['recent_posts']]
            id_list = id_list + [item['title'] for item in data['active_posts']]
            return id_list
        else:
            logger.warning(f"No existing homepage.json file found: {full_path}")
            return []

    def is_body_text_long(self, data, sent_threshold=2):
        body_text = data['_source']['body']
        body_text = preprocess_email(body_text)
        body_token = sent_tokenize(body_text)
        logger.info(f"Body sentence token length: {len(body_token)}")
        return len(body_token) > sent_threshold


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
    logger.info(f"start_date: {start_date_str}")
    logger.info(f"current_date_str: {current_date_str}")

    month_name = gen.month_dict[int(current_date.month)]
    str_month_year = f"{month_name}_{int(current_date.year)}"

    recent_data_list = []
    active_data_list = []
    random_flashback_data_list = []  # Randomly look back X years, summarize and surface a combined summary discussion with 5+ replies
    today_in_history_data_list = []  # Posts that were created on today's date on previous years

    for dev_url in dev_urls:
        all_data_df, all_data_list = elastic_search.fetch_all_data_for_url(ES_INDEX, url=dev_url)
        data_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url, start_date_str, current_date_str)
        dev_name = dev_url.split("/")[-2]
        logger.info(f"Total threads received for {dev_name}: {len(data_list)}")

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

        logger.info(f"Number of active posts collected: {len(active_data_list)}")

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

        logger.info(f"Number of recent posts collected: {len(recent_data_list)}")

        # random flashback posts - must have 5+ contributors / n_threads
        logger.info("fetching random flashback post ... ")
        while True:
            random_row_data = all_data_df.sample(n=1)
            title = random_row_data['title'].values[0]
            if title in seen_titles:
                logger.info(f"title already in active/recent posts, fetching another post randomly ...")
                continue

            # get the first post's info of this title
            df_title = all_data_df.loc[(all_data_df['title'] == title) & (all_data_df['domain'] == dev_url)]
            df_title.sort_values(by='created_at', inplace=True)
            original_post = df_title.iloc[0].to_dict()

            counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url,
                                                                                 df=df_title)
            if counts < 5:
                logger.info(f"No. of replies are less than 5, fetching another post randomly ... ")
                continue

            for i in all_data_list:
                if i['_source']['title'] == original_post['title'] and i['_source']['domain'] == original_post[
                    'domain'] and i['_source']['authors'] == original_post['authors'] and i['_source'][
                    'created_at'] == \
                        original_post['created_at'] and i['_source']['url'] == original_post['url']:
                    for author in i['_source']['authors']:
                        contributors.remove(author)
                    i['_source']['n_threads'] = counts
                    i['_source']['contributors'] = contributors
                    i['_source']['dev_name'] = dev_name
                    random_flashback_data_list.append(i)
                    break  # break for loop once we get original post of the title
            break  # break while loop as we only need one flashback post per dev_url

        logger.info(f"No. of random flashback posts collected: {len(random_flashback_data_list)}")

        # today in history posts
        logger.info(f"fetching 'Today in history' posts... ")
        logger.info(f"today is: {current_date} :: ({current_date.day}-{current_date.month})")

        all_data_df['created_at'] = pd.to_datetime(all_data_df['created_at'], errors='coerce')
        df_today_all_posts = all_data_df[(all_data_df['created_at'].dt.day == current_date.day)
                                         & (all_data_df['created_at'].dt.month == current_date.month)]

        seen_titles_today_all_posts = set()
        for idx, row in df_today_all_posts.iterrows():
            this_title = row['title']

            if this_title in seen_titles_today_all_posts:
                continue
            seen_titles_today_all_posts.add(this_title)

            this_created_at = row['created_at']

            # get the first post's info of this title
            df_title = all_data_df.loc[(all_data_df['title'] == title) & (all_data_df['domain'] == dev_url)]
            df_title.sort_values(by='created_at', inplace=True)
            original_post = df_title.iloc[0].to_dict()

            if this_created_at == original_post['created_at']:
                logger.info(f"Original post found for title: {this_title}")
                for d in all_data_list:
                    if d['_source']['title'] == original_post['title'] and d['_source']['domain'] == original_post['domain'] and d['_source']['authors'] == original_post['authors'] and d['_source']['url'] == original_post['url']:
                        counts, contributors = elastic_search.fetch_contributors_and_threads(title=title, domain=dev_url, df=df_title)
                        for author in d['_source']['authors']:
                            contributors.remove(author)
                        d['_source']['n_threads'] = counts
                        d['_source']['contributors'] = contributors
                        d['_source']['dev_name'] = dev_name
                        today_in_history_data_list.append(d)
                        break
            else:
                logger.info("Not an original post! Skipping it ...")

        logger.info(f"No. of 'Today in history' posts collected: {len(today_in_history_data_list)}")

    json_file_path = fr"static/homepage/{str_month_year}/{current_date_str}-homepage.json"
    dirname = os.path.dirname(json_file_path)
    os.makedirs(dirname, exist_ok=True)

    xml_ids = gen.get_existing_json_ids(file_path=json_file_path)
    recent_post_ids = [gen.get_id(data['_source']['title']) for data in recent_data_list]
    active_post_ids = [gen.get_id(data['_source']['title']) for data in active_data_list]

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
                    f"random flashback posts: {len(random_flashback_data_list)}, "
                    f"today in history posts: {len(today_in_history_data_list)}"
                )
                logger.info("Creating homepage.json file ... ")

                if len(active_data_list) > 0 or len(recent_data_list) > 0:
                    recent_post_summ = gen.generate_recent_posts_summary(recent_data_list)
                    logger.success(recent_post_summ)

                    # recent data
                    recent_page_data = []
                    for data in recent_data_list:
                        entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                        recent_page_data.append(entry_data)

                    # active data
                    active_page_data = []
                    for data in active_data_list:
                        entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                        active_page_data.append(entry_data)

                    # random flashback data
                    random_page_data = []
                    if len(random_flashback_data_list) > 0:
                        for data in random_flashback_data_list:
                            entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                            random_page_data.append(entry_data)

                    # today in history data
                    today_in_history_data = []
                    if len(today_in_history_data_list) > 0:
                        for data in today_in_history_data_list:
                            entry_data = gen.create_single_entry(data, look_for_combined_summary=True)
                            today_in_history_data.append(entry_data)

                    json_string = {
                        "header_summary": recent_post_summ,
                        "recent_posts": recent_page_data,
                        "active_posts": active_page_data,
                        "random_flashback_posts": random_page_data,
                        "today_in_history_posts": today_in_history_data
                    }

                    with open(json_file_path, 'w') as f:
                        f.write(json.dumps(json_string, indent=4))
                        logger.success(f"saved file: {json_file_path}")
                else:
                    logger.error(f"Data list empty! Please check the data again.")
                break

            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                time.sleep(delay)
                count += 1
                if count >= 3:
                    sys.exit(ex)
    else:
        logger.success("No change in recent posts, no need to update homepage.json file")