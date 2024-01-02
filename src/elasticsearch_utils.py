import time
from datetime import datetime
import numpy as np
import pandas as pd
from elasticsearch import Elasticsearch
from loguru import logger

from src.config import ES_CLOUD_ID, ES_USERNAME, ES_PASSWORD, ES_DATA_FETCH_SIZE


class ElasticSearchClient:
    def __init__(self,
                 es_cloud_id=ES_CLOUD_ID,
                 es_username=ES_USERNAME,
                 es_password=ES_PASSWORD,
                 es_data_fetch_size=ES_DATA_FETCH_SIZE
                 ) -> None:
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

    def fetch_data_based_on_id(self, es_index, id_str):
        logger.info(f"looking for the doc in ES with id: {id_str}")
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.info("connected to the ElasticSearch")
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "id.keyword": str(id_str)
                                }
                            }
                        ]
                    }
                }
            }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")
            return output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def extract_data_from_es(self, es_index, url, start_date_str, current_date_str,
                             exclude_combined_summary_docs=False):
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")
            if exclude_combined_summary_docs:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "prefix": {
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
                            ],
                            "must_not": [
                                {
                                    "term": {
                                        "type.keyword": "combined-summary",
                                    }
                                }
                            ]
                        }
                    }
                }
            else:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "prefix": {
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
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def filter_top_recent_posts(self, es_results, top_n):
        es_results_sorted = sorted(
            es_results,
            key=lambda x: datetime.strptime(x['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ'), reverse=True
        )
        unique_results = []
        seen_titles = set()

        # Iterate through the sorted results
        for result in es_results_sorted:
            title = result['_source']['title']
            # Only add the result if we haven't already seen the title
            if title not in seen_titles:
                unique_results.append(result)
                seen_titles.add(title)

            # Break after we've gotten top_n unique results
            if len(unique_results) >= top_n:
                break

        return unique_results

    def filter_top_active_posts(self, es_results, top_n, all_data_df):
        unique_results = []
        seen_titles = set()

        thread_dict = {}
        # create dictionary with title as key and thread count as value
        for result in es_results:
            title = result['_source']['title']
            if title not in seen_titles:
                counts, contributors = self.fetch_contributors_and_threads(title=title,
                                                                           domain=result['_source']['domain'],
                                                                           df=all_data_df)
                thread_dict[title] = counts  # add counts as value to thread_dict with key as title
                result['_source']['n_threads'] = counts  # add thread count to source
                seen_titles.add(title)

        # Use the dictionary created above, to sort the results
        es_results_sorted = sorted(
            es_results,
            key=lambda x: thread_dict[x['_source']['title']], reverse=True
        )

        seen_titles = set()
        for result in es_results_sorted:
            title = result['_source']['title']
            if title not in seen_titles:
                unique_results.append(result)
                seen_titles.add(title)

            # Break after we've gotten top_n unique results
            if len(unique_results) >= top_n:
                break

        return unique_results

    def fetch_all_data_for_url(self, es_index, url, start_date_str=None, end_date_str=None):
        logger.info(f"fetching all the data")
        output_list = []
        raw_output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.info("connected to the ElasticSearch")
            if start_date_str and end_date_str:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "prefix": {
                                        "domain.keyword": str(url)
                                    }
                                },
                                {
                                    "range": {
                                        "created_at": {
                                            "gte": f"{start_date_str}T00:00:00.000Z",
                                            "lte": f"{end_date_str}T23:59:59.999Z"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            else:
                query = {
                    "query": {
                        "match_phrase": {
                            "domain.keyword": str(url)
                        }
                    }
                }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                # Save the current batch of results
                for result in results:
                    raw_output_list.append(result)
                    output_list.append(result['_source'])

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            df = pd.DataFrame(output_list)
            logger.info(f"Total threads received for: {df.shape[0]}")
            return df, raw_output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def fetch_contributors_and_threads(self, title, domain, df):
        df_filtered = df.loc[(df['title'] == title) & (df['domain'] == domain)]
        # df_filtered = df_filtered.drop_duplicates()  # id
        counts = len(df_filtered)
        df_filtered['authors'] = df_filtered['authors'].apply(tuple)
        contributors = df_filtered['authors'].tolist()
        contributors = [i[0] for i in contributors]
        contributors = list(np.unique(contributors))
        return counts, contributors

    def fetch_data_with_empty_summary(self, es_index, url=None, start_date_str=None, current_date_str=None):
        logger.info(f"connecting ElasticSearch to fetch the docs with summary ... ")
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")

            if url and start_date_str and current_date_str:
                logger.info(f"Url: {url}, Start Date: {start_date_str}, Current Date: {current_date_str}")
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "created_at": {
                                            "gte": f"{start_date_str}T00:00:00.000Z",
                                            "lte": f"{current_date_str}T23:59:59.999Z"
                                        }
                                    }
                                },
                                {
                                    "prefix": {
                                        "domain.keyword": str(url)
                                    }
                                }
                            ],
                            "must_not": {
                                "exists": {
                                    "field": "summary"
                                }
                            }
                        }
                    }
                }
            elif url and not start_date_str and not current_date_str:
                logger.info(f"Url: {url}, Start Date: {start_date_str}, Current Date: {current_date_str}")
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "prefix": {
                                        "domain.keyword": str(url)
                                    }
                                }
                            ],
                            "must_not": {
                                "exists": {
                                    "field": "summary"
                                }
                            }
                        }
                    }
                }
            elif not url and start_date_str and current_date_str:
                logger.info(f"Url: {url}, Start Date: {start_date_str}, Current Date: {current_date_str}")
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "created_at": {
                                            "gte": f"{start_date_str}T00:00:00.000Z",
                                            "lte": f"{current_date_str}T23:59:59.999Z"
                                        }
                                    }
                                }
                            ],
                            "must_not": {
                                "exists": {
                                    "field": "summary"
                                }
                            }
                        }
                    }
                }
            else:
                logger.info(f"Url: {url}, Start Date: {start_date_str}, Current Date: {current_date_str}")
                query = {
                    "query": {
                        "bool": {
                            "must_not": {
                                "exists": {
                                    "field": "summary"
                                }
                            }
                        }
                    }
                }

            # Initialize the scroll
            scroll_response = self._es_client.search(index=es_index, body=query, size=self._es_data_fetch_size,
                                                     scroll='5m')
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            # Dump the documents into the json file
            logger.info(f"started dumping of {es_index} data in json...")
            while len(results) > 0:
                # Save the current batch of results
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            logger.warning('Could not connect to Elasticsearch')
            return output_list
