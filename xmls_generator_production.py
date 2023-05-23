import logging
import os
import re
import pandas as pd
from feedgen.feed import FeedGenerator
from tqdm import tqdm
from elasticsearch import Elasticsearch
import time
import platform
import shutil
from datetime import datetime, timedelta
import pytz
import glob
import xml.etree.ElementTree as ET

from src.gpt_utils import generate_chatgpt_summary, consolidate_chatgpt_summary
from src.config import TOKENIZER, ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE
from src.logger import setup_logger

logger = setup_logger()


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

    def extract_data_from_es(self, es_index, url, current_date_str):
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.info("connected to the ElasticSearch")
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
                                        "gte": f"{current_date_str}T00:00:00.000Z",
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
                                                     scroll='1m')
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

    def check_size_body(self, body):
        tokens = TOKENIZER.encode(body)
        # temp = len(tokens) // 2000 + 1 if len(tokens) % 2000 else 0
        # division_value = max(1, len(tokens) // 3900)  # suggested by gpt
        # temp = len(tokens) // division_value + 1 if len(tokens) % division_value else len(tokens) // division_value

        if len(tokens) % 2000 == 0:
            temp = len(tokens) // 2000
        else:
            temp = len(tokens) // 2000 + 1

        bodies = []
        sub_body_size = len(body) // temp
        for i in range(temp):
            s_num = sub_body_size * i
            e_num = (sub_body_size * i) + sub_body_size
            bodies.append(body[s_num:e_num])
        return bodies

    def gpt_api(self, body):
        summ = []
        for b in self.check_size_body(body):
            summ.append(generate_chatgpt_summary(b))
        print(len(summ))
        if len(summ) > 1:
            logger.info("consolidate summary generating")
            summ = consolidate_chatgpt_summary("\n".join(summ))
            # print(summ)
            return summ
        else:
            logger.info("Individual summary generating")
            # print("\n".join(summ))
            return "\n".join(summ)

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
        # convert the feed to an XML string
        # write the XML string to a file
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

    def generate_new_emails_df(self, dict_data, dev_url):
        columns = ['_index', '_id', '_score']
        source_cols = ['body_type', 'created_at', 'id', 'title', 'body', 'type',
                       'url', 'authors']
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        if "lightning-dev" in dev_url:
            files_list = glob.glob("./static/lightning-dev/**/*.xml", recursive=True)
        else:
            files_list = glob.glob("./static/bitcoin-dev/**/*.xml", recursive=True)

        df_dict = {}
        for col in columns:
            df_dict[col] = []
        for col in source_cols:
            df_dict[col] = []
        df_dict['update_combined_summaries'] = []

        for i in range(len(dict_data)):
            number = self.get_id(dict_data[i]["_source"]["id"])
            title = dict_data[i]["_source"]["title"]
            xml_name = self.clean_title(title)
            file_name = f"{number}_{xml_name}.xml"
            combined_filename = f"combined_{xml_name}.xml"
            xmls_list = []

            if not any(file_name in item for item in files_list):
                for col in columns:
                    df_dict[col].append(dict_data[i][col])

                for col in source_cols:
                    if "created_at" in col:
                        datetime_obj = datetime.strptime(dict_data[i]['_source'][col], "%Y-%m-%dT%H:%M:%S.%fZ")
                        timezone = pytz.UTC
                        datetime_obj = datetime_obj.replace(tzinfo=timezone)
                        df_dict[col].append(datetime_obj)
                    else:
                        df_dict[col].append(dict_data[i]['_source'][col])

                for file in files_list:
                    file = file.replace("\\", "/")
                    tree = ET.parse(file)
                    root = tree.getroot()
                    file_title = root.find('atom:entry/atom:title', namespace).text
                    if title == file_title:
                        df_dict["body_type"].append(0)
                        df_dict["id"].append(file.split("/")[-1].split("_")[0])
                        df_dict["type"].append(0)
                        df_dict["_index"].append(0)
                        df_dict["_id"].append(0)
                        df_dict["_score"].append(0)

                        df_dict["title"].append(title)
                        formatted_file_name = file.split("./static")[1]
                        logger.info(formatted_file_name)

                        tree = ET.parse(file)
                        root = tree.getroot()

                        date = root.find('atom:entry/atom:published', namespace).text
                        datetime_obj = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00")
                        timezone = pytz.UTC
                        datetime_obj = datetime_obj.replace(tzinfo=timezone)
                        df_dict["created_at"].append(datetime_obj)

                        link_element = root.find('atom:entry/atom:link', namespace)
                        link_href = link_element.get('href')
                        df_dict["url"].append(link_href)

                        author = root.find('atom:author/atom:name', namespace).text
                        author_result = re.sub(r"\d", "", author)
                        author_result = author_result.replace(":", "")
                        author_result = author_result.replace("-", "")
                        df_dict["authors"].append([author_result])

                        if combined_filename in file:
                            tree = ET.parse(file)
                            root = tree.getroot()
                            summary = root.find('atom:entry/atom:summary', namespace).text
                            df_dict["body"].append(summary)
                        else:
                            summary = root.find('atom:entry/atom:summary', namespace).text
                            df_dict["body"].append(summary)
                        df_dict["update_combined_summaries"].append(True)
                df_dict["update_combined_summaries"].append(True)

            else:
                for file in files_list:
                    file = file.replace("\\", "/")
                    tree = ET.parse(file)
                    root = tree.getroot()
                    file_title = root.find('atom:entry/atom:title', namespace).text
                    if title == file_title:
                        xmls_list.append(file)
                if len(xmls_list) > 0 and not any(combined_filename in item for item in files_list):
                    logger.info("individual summaries are present but not combined")
                    for file in xmls_list:
                        df_dict["body_type"].append(0)
                        df_dict["id"].append(file.split("/")[-1].split("_")[0])
                        df_dict["type"].append(0)
                        df_dict["_index"].append(0)
                        df_dict["_id"].append(0)
                        df_dict["_score"].append(0)

                        df_dict["title"].append(title)

                        formatted_file_name = file.split("./static")[1]
                        logger.info(f"formatted_file_name: {formatted_file_name}")

                        tree = ET.parse(file)
                        root = tree.getroot()

                        date = root.find('atom:entry/atom:published', namespace).text
                        datetime_obj = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00")
                        timezone = pytz.UTC
                        datetime_obj = datetime_obj.replace(tzinfo=timezone)
                        df_dict["created_at"].append(datetime_obj)

                        link_element = root.find('atom:entry/atom:link', namespace)
                        link_href = link_element.get('href')
                        df_dict["url"].append(link_href)

                        author = root.find('atom:author/atom:name', namespace).text
                        author_result = re.sub(r"\d", "", author)
                        author_result = author_result.replace(":", "")
                        author_result = author_result.replace("-", "")
                        df_dict["authors"].append([author_result])

                        summary = root.find('atom:entry/atom:summary', namespace).text
                        df_dict["body"].append(summary)
                        df_dict["update_combined_summaries"].append(True)
        print(df_dict)
        emails_df = pd.DataFrame(df_dict)

        return emails_df

    def start(self, dict_data, url):
        if len(dict_data) > 0:
            emails_df = self.generate_new_emails_df(dict_data, url)
            if len(emails_df) > 0:
                print(emails_df)
                print(emails_df["url"].values)
                emails_df['created_at_org'] = emails_df['created_at']

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
                        logger.info(f"{file_path} already exist")
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

                # combine_summary_xml
                # Get the operating system name
                os_name = platform.system()
                logger.info(f"Operating System: {os_name}")
                titles = emails_df.sort_values('created_at')['title'].unique()
                logger.info(f"Total titles in data: {len(titles)}")
                for title_idx, title in tqdm(enumerate(titles)):
                    title_df = emails_df[emails_df['title'] == title]
                    if len(title_df) < 1:
                        continue
                    if len(title_df) == 1:
                        generate_local_xml(title_df.iloc[0], "0", url)
                        continue
                    # body = title_df['body'].apply(str).tolist() + old_files_data_dict["summary_list"]
                    combined_body = '\n\n'.join(title_df['body'].apply(str))
                    # combined_body = '\n\n'.join(body)
                    xml_name = self.clean_title(title)
                    # combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1)) + old_files_data_dict["files_links"]
                    combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1))
                    combined_authors = list(
                        title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1))
                        # title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1)) + old_files_data_dict["author_list"]

                    month_year_group = \
                    title_df.groupby([title_df['created_at'].dt.month, title_df['created_at'].dt.year])["update_combined_summaries"]

                    flag = False
                    std_file_path = ''
                    for idx, (month_year, update_combine_flag) in enumerate(month_year_group):
                        logger.info(f"###### {month_year}")
                        month_name = self.month_dict[int(month_year[0])]
                        str_month_year = f"{month_name}_{month_year[1]}"
                        if "bitcoin-dev" in url:
                            file_path = f"static/bitcoin-dev/{str_month_year}/combined_{xml_name}.xml"
                        else:
                            file_path = f"static/lightning-dev/{str_month_year}/combined_{xml_name}.xml"
                        if os.path.exists(file_path) and not update_combine_flag[0]:
                            logger.info(f"Skiping Combined summary generation file already exists. {file_path}")
                            continue
                        combined_summary = self.create_summary(combined_body)
                        feed_data = {
                            'id': "2",
                            'title': 'Combined summary - ' + title,
                            'authors': combined_authors,
                            'url': title_df.iloc[0]['url'],
                            'links': combined_links,
                            'created_at': title_df.iloc[0]['created_at_org'],
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
            else:
                logger.info("No new files are found")
        else:
            logger.info("No input data found")


if __name__ == "__main__":
    gen = GenerateXML()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)
    dev_url = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"

    # current_date_str = "2021-08-21"
    current_date_str = "2021-09-30"
    if not current_date_str:
        current_date_str = datetime.now().strftime("%Y-%m-%d")

    data_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url, current_date_str)
    print(len(data_list))
    print(data_list)

    delay = 50

    while True:
        try:
            gen.start(data_list, dev_url)
            break
        except Exception as ex:
            print(ex)
            time.sleep(delay)
