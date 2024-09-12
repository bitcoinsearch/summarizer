import tqdm
import traceback
from loguru import logger
import glob
import os
from collections import defaultdict
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import XMLReader
from src.utils import remove_timestamps_from_author_names, summarizer_log_csv

if __name__ == "__main__":

    inserted_count = defaultdict(set)
    updated_count = defaultdict(set)
    no_changes_count = defaultdict(set)
    unique_urls = set()
    error_message = None
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

    except Exception as ex:
        error_occurred = True
        error_message = f"Error:{ex}\n{traceback.format_exc()}"
        logger.error(f"Error Message: {error_message}")
        logger.error(f"Process failed.")

    finally:
        summarizer_log_csv(file_name='push_combined_summary_to_es',
                           domain=list(unique_urls),
                           inserted=sum(len(inserted_count[url]) for url in unique_urls),
                           updated=sum(len(updated_count[url]) for url in unique_urls),
                           no_changes=sum(len(no_changes_count[url]) for url in unique_urls),
                           error=error_message)

    logger.success("Process Complete.")
