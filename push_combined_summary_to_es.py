import tqdm
import traceback
from loguru import logger
import glob
import os

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader
from src.utils import remove_timestamps_from_author_names

if __name__ == "__main__":

    REMOVE_TIMESTAMPS_IN_AUTHORS = True

    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient()

    total_combined_files = []
    static_dirs = [
        'bitcoin-dev',
        'lightning-dev',
        'delvingbitcoin'
    ]
    pattern = "combined*.xml"

    for static_dir in static_dirs:
        combined_files = glob.glob(f"static/{static_dir}/**/{pattern}")
        total_combined_files.extend(combined_files)
    logger.info(f"Total combined summary files: {(len(total_combined_files))}")

    # get unique combined file paths
    total_combined_files_dict = {os.path.splitext(os.path.basename(i))[0]: i for i in total_combined_files}

    logger.info(f"Total unique combined summary files: {len(total_combined_files_dict)}")

    count_new = 0
    count_updated = 0

    for file_name, full_path in tqdm.tqdm(total_combined_files_dict.items()):
        try:
            # get data from xml file
            xml_file_data = xml_reader.read_xml_file(full_path)

            if REMOVE_TIMESTAMPS_IN_AUTHORS:
                # remove timestamps from author's names and collect unique names only
                xml_file_data['authors'] = remove_timestamps_from_author_names(xml_file_data['authors'])

            latest_updated_at = xml_file_data['updated_at']

            # check updated_at in ES doc
            doc_id = xml_file_data['id']
            doc = elastic_search.document_view(index_name=ES_INDEX, doc_id=doc_id)
            prev_updated_at = doc['_source']['updated_at']

            # sync the ES doc if there is any update in the XML File, else skip it
            if latest_updated_at == prev_updated_at:
                continue

            res = elastic_search.es_client.update(
                index=ES_INDEX,
                id=file_name,
                body={
                    'doc': xml_file_data,
                    'doc_as_upsert': True
                }
            )

            logger.success(f"Version: {res['_version']}, Result: {res['result']}, ID: {res['_id']}, Domain: {xml_file_data['domain']}")
            if res['result'] == 'created':
                count_new += 1
            if res['result'] == 'updated':
                count_updated += 1

        except Exception as ex:
            error_message = f"Error occurred: {ex} \n{traceback.format_exc()}"
            logger.error(error_message)

    logger.info(f"Inserted {count_new} new documents, Updated {count_updated} documents")