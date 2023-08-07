import os
import re
import traceback
import pandas as pd
from feedgen.feed import FeedGenerator
from tqdm import tqdm
from elasticsearch import Elasticsearch
import time
import ast
import pytz
import platform
import shutil
from datetime import datetime
import xml.etree.ElementTree as ET
from src.utils import preprocess_email
from src.gpt_utils import generate_chatgpt_summary, consolidate_chatgpt_summary
from src.config import TOKENIZER, ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE
from loguru import logger
import warnings
warnings.filterwarnings("ignore")


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

    def extract_data_from_es(self, es_index, url):
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.info("connected to the ElasticSearch")
            query = {
                "query": {
                    "match_phrase": {
                        "domain": str(url)
                    }
                }
            }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='1m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                # Save the current batch of results
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='1m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None


class GenerateXML:
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

        print(f"Total chunks: {len(chunks)}")

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
                        break
                    print(f"Chunk summary ran into error: {traceback.format_exc()}")

        return summaries

    def recursive_summary(self, body, tokens_per_sub_body, max_length):
        summaries = self.get_summary_chunks(body, tokens_per_sub_body)

        summary_length = sum([len(TOKENIZER.encode(s)) for s in summaries])

        print(f"Summary length: {summary_length}")
        print(f"Max length: {max_length}")

        if summary_length > max_length:
            print("entering in recursion")
            return self.recursive_summary("".join(summaries), tokens_per_sub_body, max_length)
        else:
            return summaries

    def gpt_api(self, body):
        body_length_limit = 2800
        tokens_per_sub_body = 2700
        summaries = self.recursive_summary(body, tokens_per_sub_body, body_length_limit)

        if len(summaries) > 1:
            print("Consolidate summary generating")
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
                        break
                    print(f"Consolidate summary ran into error {traceback.format_exc()}.")
            return consolidated_summaries

        else:
            print("Individual summary generating")
            return "\n".join(summaries)

    def create_summary(self, body):
        summ = self.gpt_api(body)
        return summ

    def create_folder(self, month_year):
        os.makedirs(month_year, exist_ok=True)

    def generate_xml(self, feed_data, xml_file):
        # create feed generator
        fg = FeedGenerator()
        fg.id(feed_data['id'])
        fg.title(feed_data['title'])
        for author in feed_data['authors']:
            fg.author({'name': author})
        for link in feed_data['links']:
            fg.link(href=link, rel='alternate')
        # add entries to the feed
        fe = fg.add_entry()
        fe.id(feed_data['id'])
        fe.title(feed_data['title'])
        fe.link(href=feed_data['url'], rel='alternate')
        fe.published(feed_data['created_at'])
        fe.summary(feed_data['summary'])

        # generate the feed XML
        feed_xml = fg.atom_str(pretty=True)
        with open(xml_file, 'wb') as f:
            f.write(feed_xml)

    def clean_title(self, xml_name):
        special_characters = ['/', ':', '@', '#', '$', '*', '&', '<', '>', '\\', '?']
        xml_name = re.sub(r'[^A-Za-z0-9]+', '-', xml_name)
        for sc in special_characters:
            xml_name = xml_name.replace(sc, "-")
        return xml_name

    def get_id(self, id):
        return str(id).split("-")[-1]

    def convert_to_utc_zulo_timestamp(self, date_str):
        datetime_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        timezone = pytz.UTC
        datetime_obj = datetime_obj.replace(tzinfo=timezone)
        return datetime_obj

    def start(self, dict_data, url):
        columns = ['_index', '_id', '_score']
        source_cols = ['body_type', 'created_at', 'id', 'title', 'body', 'type',
                       'url', 'authors']
        df_list = []
        for i in range(len(dict_data)):
            df_dict = {}
            for col in columns:
                df_dict[col] = dict_data[i][col]
            for col in source_cols:
                df_dict[col] = dict_data[i]['_source'][col]
            df_list.append(df_dict)
        emails_df = pd.DataFrame(df_list)

        emails_df['authors'] = emails_df['authors'].apply(self.convert_to_tuple)
        emails_df = emails_df.drop_duplicates()
        emails_df['authors'] = emails_df['authors'].apply(self.preprocess_authors_name)
        logger.info(f"Shape of emails_df: {emails_df.shape}")
        emails_df['body'] = emails_df['body'].apply(preprocess_email)

        emails_df['created_at_org'] = emails_df['created_at']
        emails_df['created_at'] = emails_df['created_at'].apply(self.convert_to_utc_zulo_timestamp)

        def generate_local_xml(cols, combine_flag, url):
            month_name = self.month_dict[int(cols['created_at'].month)]
            str_month_year = f"{month_name}_{int(cols['created_at'].year)}"
            if "bitcoin-dev" in url:
                if not os.path.exists(f"static/bitcoin-dev/{str_month_year}"):
                    self.create_folder(f"static/bitcoin-dev/{str_month_year}")
                number = self.get_id(cols['id'])
                xml_name = self.clean_title(cols['title'])
                file_path = f"static/bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml"
            else:
                if not os.path.exists(f"static/lightning-dev/{str_month_year}"):
                    self.create_folder(f"static/lightning-dev/{str_month_year}")
                number = self.get_id(cols['id'])
                xml_name = self.clean_title(cols['title'])
                file_path = f"static/lightning-dev/{str_month_year}/{number}_{xml_name}.xml"
            if os.path.exists(file_path):
                if "bitcoin-dev" in url:
                    link = f'bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml'
                else:
                    link = f'lightning-dev/{str_month_year}/{number}_{xml_name}.xml'
                return link
            summary = self.create_summary(cols['body'])
            feed_data = {
                'id': combine_flag,
                'title': cols['title'],
                'authors': [f"{cols['authors'][0]} {cols['created_at']}"],
                'url': cols['url'],
                'links': [],
                'created_at': cols['created_at_org'],
                'summary': summary
            }
            self.generate_xml(feed_data, file_path)
            if "bitcoin-dev" in url:
                link = f'bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml'
            else:
                link = f'lightning-dev/{str_month_year}/{number}_{xml_name}.xml'
            return link

        def get_summary_from_file(cols, url):
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            month_name = self.month_dict[int(cols['created_at'].month)]
            str_month_year = f"{month_name}_{int(cols['created_at'].year)}"
            if "bitcoin-dev" in url:
                if not os.path.exists(f"static/bitcoin-dev/{str_month_year}"):
                    self.create_folder(f"static/bitcoin-dev/{str_month_year}")
                number = self.get_id(cols['id'])
                xml_name = self.clean_title(cols['title'])
                file_path = f"static/bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml"
            else:
                if not os.path.exists(f"static/lightning-dev/{str_month_year}"):
                    self.create_folder(f"static/lightning-dev/{str_month_year}")
                number = self.get_id(cols['id'])
                xml_name = self.clean_title(cols['title'])
                file_path = f"static/lightning-dev/{str_month_year}/{number}_{xml_name}.xml"
            if os.path.exists(file_path):
                tree = ET.parse(file_path)
                root = tree.getroot()
                summary = root.find('atom:entry/atom:summary', namespace).text
                return summary
            else:
                return cols['body']

        # combine_summary_xml
        # Get the operating system name
        os_name = platform.system()
        print("Operating System:", os_name)
        titles = emails_df.sort_values('created_at')['title'].unique()
        print("Total titles in data: ", len(titles))
        for title_idx, title in tqdm(enumerate(titles)):
            # if title_idx == 50:
            #     break
            title_df = emails_df[emails_df['title'] == title]
            title_df = title_df.sort_values(by='created_at', ascending=False)
            if len(title_df) < 1:
                continue
            if len(title_df) == 1:
                generate_local_xml(title_df.iloc[0], "0", url)
                continue
            xml_name = self.clean_title(title)
            combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1))
            # combined_authors = list(title_df['authors'].apply(lambda x: x[0]))
            combined_authors = list(
                title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1))
            combined_body = '\n\n'.join(filter(None, list(title_df.apply(get_summary_from_file, args=(url,), axis=1))))

            month_year_group = title_df.groupby([title_df['created_at'].dt.month, title_df['created_at'].dt.year])

            flag = False
            std_file_path = ''
            for idx, (month_year, _) in enumerate(month_year_group):
                print(f"###### {month_year}")
                # if idx == 5:
                #     break
                month_name = self.month_dict[int(month_year[0])]
                str_month_year = f"{month_name}_{month_year[1]}"
                if "bitcoin-dev" in url:
                    file_path = f"static/bitcoin-dev/{str_month_year}/combined_{xml_name}.xml"
                else:
                    file_path = f"static/lightning-dev/{str_month_year}/combined_{xml_name}.xml"

                if os.path.exists(file_path):
                    print(f"Skiping Combined summary generation file already exists. {file_path}")
                    continue
                combined_summary = self.create_summary(combined_body)
                feed_data = {
                    'id': "2",
                    'title': 'Combined summary - ' + title,
                    'authors': combined_authors,
                    'url': title_df.iloc[0]['url'],
                    'links': combined_links,
                    'created_at': self.add_utc_if_not_present(title_df.iloc[0]['created_at_org']),
                    'summary': combined_summary
                }
                if not flag:
                    self.generate_xml(feed_data, file_path)
                    std_file_path = file_path
                    flag = True
                else:
                    if os_name == "Windows":
                        shutil.copy(std_file_path, file_path)
                    elif os_name == "Linux":
                        os.system(f"cp {std_file_path} {file_path}")

    def convert_to_tuple(self, x):
        try:
            if isinstance(x, str):
                x = ast.literal_eval(x)
            return tuple(x)
        except ValueError:
            return (x,)

    def preprocess_authors_name(self, author_tuple):
        author_tuple = tuple(s.replace('+', '').strip() for s in author_tuple)
        return author_tuple

    def add_utc_if_not_present(self, datetime_str):
        try:
            datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            datetime_obj = datetime_obj.replace(tzinfo=pytz.UTC)
        except ValueError:
            datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
            timezone = pytz.UTC
            datetime_obj = datetime_obj.replace(tzinfo=timezone)
        return datetime_obj.isoformat(" ")


if __name__ == "__main__":
    gen = GenerateXML()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)
    # dev_url = "https://lists.linuxfoundation.org/pipermail/lightning-dev/"
    dev_url = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"
    data_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url)

    # data_list = data_list[:15]

    delay = 5

    while True:
        try:
            gen.start(data_list, dev_url)
            break
        except Exception as ex:
            logger.error(ex)
            time.sleep(delay)

