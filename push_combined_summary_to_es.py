import tqdm
import traceback
from loguru import logger
import glob
import os
from collections import defaultdict
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader
from src.utils import remove_timestamps_from_author_names, log_csv

if __name__ == "__main__":

    inserted_count = defaultdict(set)
    updated_count = defaultdict(set)
    no_changes_count = defaultdict(set)
    unique_urls = set()
    error_occurred = False
    error_message = "---"
    try:
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
        logger.info(f"Total combined files: {(len(total_combined_files))}")

        total_combined_files_dict = {os.path.splitext(os.path.basename(i))[0]: i for i in total_combined_files}

        logger.info(f"Total unique combined files: {len(total_combined_files_dict)}")

        for file_name, full_path in tqdm.tqdm(total_combined_files_dict.items()):
            try:

                xml_file_data = xml_reader.read_xml_file(full_path)
                url = xml_file_data['domain']
                unique_urls.add(url)

                if REMOVE_TIMESTAMPS_IN_AUTHORS:

                    xml_file_data['authors'] = remove_timestamps_from_author_names(xml_file_data['authors'])

                body = {
                    'doc': xml_file_data,
                    'doc_as_upsert': True
                }

                res = elastic_search.upsert_document(index_name=ES_INDEX,
                                                     doc_id=file_name,
                                                     doc_body=body)

                if res['result'] == 'created' or res['result'] == 'updated':
                    updated_count[url].add(res['_id'])
                elif res['result'] == 'noop':
                    no_changes_count[url].add(res['_id'])

            except Exception as ex:
                logger.error(f"Error occurred: {ex} \n{traceback.format_exc()}")
                logger.warning(full_path)

        logger.success(f"Process complete.")
        logger.success(f"Error Occurred: {error_occurred}")

    except Exception as ex:
        error_occurred = True
        error_message = str(ex)
        logger.error(f"Error Occurred: {error_occurred}")
        logger.error(f"Error Message: {error_message}")
        logger.error(f"Process failed.")

    finally:
        for url in unique_urls:
            log_csv(file_name='push_combined_summary_to_es',
                    url=url,
                    inserted=len(inserted_count[url]),
                    updated=len(updated_count[url]),
                    no_changes=len(no_changes_count[url]),
                    error=str(error_occurred),
                    error_log=error_message)

            logger.info(f"URL:->{url}"
                        f" :: Inserted Count:->{len(inserted_count[url])}"
                        f" :: Updated Count:->{len(updated_count[url])}"
                        f" :: No Changed Count:->{len(no_changes_count[url])}.")

    logger.success("Process Complete.")
