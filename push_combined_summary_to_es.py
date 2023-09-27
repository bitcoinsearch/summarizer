import re
from elasticsearch import Elasticsearch
import time
from datetime import datetime, timedelta
from loguru import logger
import xml.etree.ElementTree as ET
# import os
from dotenv import load_dotenv
import warnings
# import pytz
# import tqdm
import glob

from src.config import ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_INDEX, ES_DATA_FETCH_SIZE

warnings.filterwarnings("ignore")
load_dotenv()


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

    def read_xml_file(self, full_path):
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        tree = ET.parse(full_path)
        root = tree.getroot()
        title = root.findall(".//atom:entry/atom:title", namespaces)
        summary = root.findall(".//atom:entry/atom:summary", namespaces)
        published = root.findall(".//atom:entry/atom:published", namespaces)
        link = root.findall(".//atom:entry/atom:link", namespaces)
        authors = root.findall('atom:author/atom:name', namespaces)
        author_list = [author.text for author in authors]
        domain = '/'.join(str(link[0].get('href')).split("/")[:-2])
        # indexed_at = datetime.
        # published_at = datetime.strptime(data['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        # published_at = pytz.UTC.localize(published_at)
        return {
            'id': self.clean_title(title[0].text),
            'title': title[0].text if title else None,
            'summary': summary[0].text if summary else None,
            'body': summary[0].text if summary else None,
            'url': link[0].get('href') if link else None,
            'author_list': author_list if author_list else None,
            'created_at': published[0].text if published else None,
            'body_type': "combined-summary",
            'domain': domain if domain else None
        }


if __name__ == "__main__":

    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient(es_cloud_id=ES_CLOUD_ID, es_username=ES_USERNAME,
                                         es_password=ES_PASSWORD)

    total_combined_files = []
    static_dirs = ['bitcoin-dev', 'lightning-dev']
    pattern = "combined*.xml"
    for static_dir in static_dirs:
        combined_files = glob.glob(f"static/{static_dir}/**/{pattern}")
        total_combined_files.extend(combined_files)
    logger.info(f"Total combined files: {(len(total_combined_files))}")

    # get unique combined files and it's full path
    total_combined_files_dict = {i.split("\\")[-1]: i for i in total_combined_files}
    logger.info(f"Total unique combined files: {len(total_combined_files_dict)}")

    for file_name, full_path in total_combined_files_dict.items():
        logger.info(full_path)

        xml_file_data = xml_reader.read_xml_file(full_path)
        # from pprint import pprint
        # pprint(xml_file_data)

        # update data to es index
        res = elastic_search.es_client.index(index=ES_INDEX, id=3, body=xml_file_data)
        logger.success(res)

        break
