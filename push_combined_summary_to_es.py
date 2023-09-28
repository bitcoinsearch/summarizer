import tqdm
import re
from elasticsearch import Elasticsearch
import traceback
from datetime import datetime, timezone
from loguru import logger
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import warnings
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
        title = root.findall(".//atom:entry/atom:title", namespaces)[0].text
        title_for_id = title.replace('Combined summary - ', '')
        id = 'combined_' + self.clean_title(title_for_id)
        summary = root.findall(".//atom:entry/atom:summary", namespaces)[0].text
        published = root.findall(".//atom:entry/atom:published", namespaces)[0].text
        link = root.findall(".//atom:entry/atom:link", namespaces)[0].get('href')
        authors = root.findall('atom:author/atom:name', namespaces)
        author_list = [author.text for author in authors]
        domain = '/'.join(str(link).split("/")[:-2])
        indexed_at = ((datetime.now(timezone.utc)).replace(microsecond=0)).isoformat()
        return {
            'id': id if id else None,
            'title': title if title else None,
            'summary': summary if summary else None,
            'body': summary if summary else None,
            'url': link if link else None,
            'author_list': author_list if author_list else None,
            'created_at': published if published else None,
            'body_type': "combined-summary",
            'domain': domain if domain else None,
            'indexed_at': indexed_at if indexed_at else None
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

    # get unique combined file paths
    total_combined_files_dict = {i.split("\\")[-1][:-4]: i for i in total_combined_files}
    logger.info(f"Total unique combined files: {len(total_combined_files_dict)}")

    for file_name, full_path in tqdm.tqdm(total_combined_files_dict.items()):
        try:
            # get data from xml file
            xml_file_data = xml_reader.read_xml_file(full_path)

            # check if doc exist in ES index
            doc_exists = elastic_search.es_client.exists(index=ES_INDEX, id=file_name)

            # insert the doc in ES index if it does not exist, else update it
            if not doc_exists:
                res = elastic_search.es_client.index(
                    index=ES_INDEX,
                    id=file_name,
                    body=xml_file_data
                )
                logger.success(res)
            else:
                res = elastic_search.es_client.update(
                    index=ES_INDEX,
                    id=file_name,
                    body={'doc': xml_file_data}
                )
                logger.success(res)

        except Exception as ex:
            error_message = f"Error occurred: {ex} \n{traceback.format_exc()}"
            logger.error(error_message)

    logger.success(f"Process complete.")
