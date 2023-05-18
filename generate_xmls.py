import os
import re
import pandas as pd
from feedgen.feed import FeedGenerator
from tqdm import tqdm
from elasticsearch import Elasticsearch
import time
import platform
import shutil
from datetime import datetime
from src.gpt_utils import generate_chatgpt_summary, consolidate_chatgpt_summary
from src.config import TOKENIZER, ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE
from src.logger import LOGGER


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
            LOGGER.info("connected to the ElasticSearch")
            # Update the query to filter by domain
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
            LOGGER.info(f"Starting dumping of {es_index} data in json...")
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

            LOGGER.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            LOGGER.info('Could not connect to Elasticsearch')
            return None


class GenerateXML:
    def __init__(self) -> None:
        self.month_dict = {
            1: "Jan", 2: "Feb", 3: "March", 4: "April", 5: "May", 6: "June",
            7: "July", 8: "Aug", 9: "Sept", 10: "Oct", 11: "Nov", 12: "Dec"
        }

    def check_size_body(self, body):
        tokens = TOKENIZER.encode(body)
        temp = len(tokens) // 2000 + 1 if len(tokens) % 2000 else 0
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
        if len(summ) > 1:
            print("consolidate summary generating")
            summ = consolidate_chatgpt_summary("\n".join(summ))
            return summ
        else:
            print("Individual summary generating")
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

    def start(self, dict_data, url):
        # data = open(json_path, "r")
        # dict_data = []
        # for line in data:
        #     dict_data.append(json.loads(line))

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

        emails_df['created_at_org'] = emails_df['created_at']
        emails_df['created_at'] = pd.to_datetime(emails_df['created_at'], format="%Y-%m-%dT%H:%M:%S.%fZ")

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

        # combine_summary_xml
        # Get the operating system name
        os_name = platform.system()
        print("Operating System:", os_name)
        titles = emails_df.sort_values('created_at')['title'].unique()
        for title_idx, title in tqdm(enumerate(titles)):
            # if title_idx == 50:
            #     break
            title_df = emails_df[emails_df['title'] == title]
            if len(title_df) < 1:
                continue
            if len(title_df) == 1:
                generate_local_xml(title_df.iloc[0], "0", url)
                continue
            combined_body = '\n\n'.join(title_df['body'].apply(str))
            combined_summary = self.create_summary(combined_body)
            xml_name = self.clean_title(title)
            combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1))
            # combined_authors = list(title_df['authors'].apply(lambda x: x[0]))
            combined_authors = list(
                title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1))
            feed_data = {
                'id': "2",
                'title': 'Combined summary - ' + title,
                'authors': combined_authors,
                'url': title_df.iloc[0]['url'],
                'links': combined_links,
                'created_at': title_df.iloc[0]['created_at_org'],
                'summary': combined_summary
            }

            month_year_group = title_df.groupby([title_df['created_at'].dt.month, title_df['created_at'].dt.year])

            flag = False
            std_file_path = ''
            for idx, (month_year, _) in enumerate(month_year_group):
                # if idx == 5:
                #     break
                month_name = self.month_dict[int(month_year[0])]
                str_month_year = f"{month_name}_{month_year[1]}"
                if "bitcoin-dev" in url:
                    file_path = f"static/bitcoin-dev/{str_month_year}/combined_{xml_name}.xml"
                else:
                    file_path = f"static/lightning-dev/{str_month_year}/combined_{xml_name}.xml"
                # if os.path.exists(file_path):
                #     continue
                if not flag:
                    self.generate_xml(feed_data, file_path)
                    std_file_path = file_path
                    flag = True
                else:
                    if os_name == "Windows":
                        shutil.copy(std_file_path, file_path)
                    elif os_name == "Linux":
                        os.system(f"cp {std_file_path} {file_path}")


if __name__ == "__main__":
    gen = GenerateXML()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)
    # dev_url = "https://lists.linuxfoundation.org/pipermail/lightning-dev/"
    dev_url = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"
    data_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url)

    str_month_year_list = []
    for data in data_list:
        all_value = data["_source"]
        datetime_obj = datetime.strptime(all_value['created_at'], "%Y-%m-%dT%H:%M:%S.%fZ")
        month_name = gen.month_dict[int(datetime_obj.month)]
        str_month_year = f"{month_name}_{int(datetime_obj.year)}"
        if str_month_year not in str_month_year_list:
            str_month_year_list.append(str_month_year)

    if "lightning-dev" in dev_url:
        dev_folder = os.path.join("./static", "lightning-dev")
    else:
        dev_folder = os.path.join("./static", "bitcoin-dev")

    delay = 45

    while True:
        extracted_month_year_list = os.listdir(dev_folder)

        # if len(extracted_month_year_list) == len(str_month_year_list):
        #     break
        try:
            gen.start(data_list, dev_url)
            break
        except Exception as ex:
            print(ex)
            time.sleep(delay)

