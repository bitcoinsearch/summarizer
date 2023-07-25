import re
import pandas as pd
import tqdm
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

from src.config import TOKENIZER, ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE

warnings.filterwarnings("ignore")
load_dotenv()

logger.add("push_summary_back_to_es.log", rotation="12:00")     # New file is created each day at noon

# if set to True, it will use chatgpt model ("gpt-3.5-turbo") for all the completions
CHATGPT = True

# COMPLETION_MODEL - only applicable if CHATGPT is set to False
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

    def fetch_all_data_for_url(self, es_index, url):
        logger.info(f"fetching all the data")
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
                    output_list.append(result['_source'])

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
            scroll_response = self._es_client.search(
                index=es_index,
                body=query,
                size=self._es_data_fetch_size,
                scroll='1m'
            )
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

    @property
    def es_client(self):
        return self._es_client


class XMLReader:
    def __init__(self) -> None:
        self.month_dict = {
            1: "Jan", 2: "Feb", 3: "March", 4: "April", 5: "May", 6: "June",
            7: "July", 8: "Aug", 9: "Sept", 10: "Oct", 11: "Nov", 12: "Dec"
        }

    def get_id(self, id):
        return str(id).split("-")[-1]

    def clean_title(self, xml_name):
        special_characters = ['/', ':', '@', '#', '$', '*', '&', '<', '>', '\\', '?']
        xml_name = re.sub(r'[^A-Za-z0-9]+', '-', xml_name)
        for sc in special_characters:
            xml_name = xml_name.replace(sc, "-")
        return xml_name

    def get_xml_summary(self, data, dev_name):
        number = self.get_id(data["_source"]["id"])
        title = data["_source"]["title"]
        xml_name = self.clean_title(title)
        published_at = datetime.strptime(data['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        published_at = pytz.UTC.localize(published_at)
        month_name = self.month_dict[int(published_at.month)]
        str_month_year = f"{month_name}_{int(published_at.year)}"
        # dev_name = data['_source']['dev_name']

        current_directory = os.getcwd()
        file_path = f"static/{dev_name}/{str_month_year}/{number}_{xml_name}.xml"
        full_path = os.path.join(current_directory, file_path)

        if os.path.exists(full_path):
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(full_path)
            root = tree.getroot()
            summ_list = root.findall(".//atom:entry/atom:summary", namespaces)
            summ = "\n".join([summ.text for summ in summ_list])
            return summ
        else:
            logger.warning(f"No xml file found: {full_path}")
            return None


if __name__ == "__main__":

    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)

    dev_urls = [
        "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/",
        "https://lists.linuxfoundation.org/pipermail/lightning-dev/"
    ]

    current_date_str = None
    if not current_date_str:
        current_date_str = datetime.now().strftime("%Y-%m-%d")

    start_date = datetime.now() - timedelta(days=15)
    start_date_str = start_date.strftime("%Y-%m-%d")
    logger.info(f"start_date: {start_date_str}")
    logger.info(f"current_date_str: {current_date_str}")

    for dev_url in dev_urls:
        docs_list = elastic_search.extract_data_from_es(ES_INDEX, dev_url, start_date_str, current_date_str)
        dev_name = dev_url.split("/")[-2]
        logger.success(f"Total threads received for {dev_name}: {len(docs_list)}")

        for doc in docs_list:
            doc_id = doc['_id']
            doc_index = doc['_index']
            if not doc['_source'].get('summary'):

                # get the summary from stored xml file
                xml_summary = xml_reader.get_xml_summary(doc, dev_name)

                if xml_summary:
                    # logger.info(f"updating index with found summary: {xml_summary}")

                    # update the document
                    elastic_search.es_client.update(
                        index=doc_index,
                        id=doc_id,
                        body={
                            'doc': {
                                "summary": xml_summary
                            }
                        }
                    )
                    logger.success(f"Document with ID: {doc_id} has been updated.")

            else:
                logger.info(f"Document with ID: {doc_id} already has a summary.")

            # break
        # break

    logger.success(f"Process complete.")
    