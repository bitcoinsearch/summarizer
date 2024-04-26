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

    # Instantiating objects for reading XML and connecting to ElasticSearch
    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient()

    # Static directory names to look into for respective combined summary xml files
    static_dirs = [
        'bitcoin-dev',
        'lightning-dev',
        'delvingbitcoin'
    ]
    pattern = "combined*.xml"

    total_combined_files = []
    for static_dir in static_dirs:
        combined_files = glob.glob(f"static/{static_dir}/**/{pattern}")
        total_combined_files.extend(combined_files)
    logger.info(f"Total combined files: {(len(total_combined_files))}")

    # Get unique combined file paths
    total_combined_files_dict = {os.path.splitext(os.path.basename(i))[0]: i for i in total_combined_files}
    logger.info(f"Total unique combined files: {len(total_combined_files_dict)}")

    # Loop through all locally stored combined summary XML files and insert/update them accordingly
    for file_name, full_path in tqdm.tqdm(total_combined_files_dict.items()):
        try:
            # Get data from xml file
            xml_file_data = xml_reader.read_xml_file(full_path)

            if REMOVE_TIMESTAMPS_IN_AUTHORS:
                # Remove timestamps from author's names and collect unique names only
                xml_file_data['authors'] = remove_timestamps_from_author_names(xml_file_data['authors'])

            # Check if doc exist in ES index
            doc_exists = elastic_search.es_client.exists(index=ES_INDEX, id=file_name)

            # Insert the doc in ES index if it does not exist, else update it
            if not doc_exists:
                res = elastic_search.es_client.index(
                    index=ES_INDEX,
                    id=file_name,
                    body=xml_file_data
                )
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
