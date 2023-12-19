import tqdm
import traceback
from loguru import logger
import glob
import os

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader


if __name__ == "__main__":

    xml_reader = XMLReader()
    elastic_search = ElasticSearchClient()

    total_combined_files = []
    static_dirs = ['bitcoin-dev', 'lightning-dev']
    pattern = "combined*.xml"
    for static_dir in static_dirs:
        combined_files = glob.glob(f"static/{static_dir}/**/{pattern}")
        total_combined_files.extend(combined_files)
    logger.info(f"Total combined files: {(len(total_combined_files))}")

    # get unique combined file paths
    total_combined_files_dict = {os.path.splitext(os.path.basename(i))[0]: i for i in total_combined_files}

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
