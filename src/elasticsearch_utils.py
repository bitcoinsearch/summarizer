import time
from datetime import datetime

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import scan
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

    def get_domain_counts(self, index_name, domain):
        """Function to get the total counts for the given 'domain' field from Elasticsearch index."""
        body = {
            "query": {
                "term": {
                    "domain.keyword": domain
                }
            }
        }

        try:
            resp = self.es_client.count(index=index_name, body=body)
            return resp['count']
        except Exception as e:
            logger.error(f"Error fetching domain counts: {e}")
            return None

    @property
    def es_client(self):
        return self._es_client

    def upsert_document(self, index_name, doc_id, doc_body):

        script = {
            "source": "ctx._source.putAll(params)",
            "params": doc_body
        }

        request_body = {
            "scripted_upsert": True,
            "script": script,
            "upsert": doc_body
        }

        # Perform the upsert operation
        response = self._es_client.update(index=index_name, id=doc_id, body=request_body)
        return response

    def get_domain_query(self, url):
        if isinstance(url, list):
            domain_query = {"terms": {"domain.keyword": url}}
        else:
            domain_query = {"term": {"domain.keyword": url}}
        return domain_query

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

    def fetch_data_based_on_title(self, es_index, title, url):
        logger.info(f"looking for title: {title}")
        output_list = []

        if self._es_client.ping():
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match_phrase":
                                    {
                                        "title.keyword": title
                                    }
                            },
                            {
                                "term":
                                    {
                                        "domain.keyword": str(url)
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

            while len(results) > 0:
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            return output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def extract_data_from_es(self, es_index, url, start_date_str, current_date_str,
                             exclude_combined_summary_docs=False):
        """
        Fetches and extracts documents from a specified Elasticsearch index based on URL,
        date range, and an optional exclusion flag for combined summary documents.
        The method returns a list of documents that match the query criteria.
        """
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")

            # Construct a search query to filter documents by domain,
            # date range (start to end date) and optionally exclude
            # 'combined-summary' documents
            domain_query = self.get_domain_query(url)

            if exclude_combined_summary_docs:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                domain_query,
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
                                        "type.keyword": "combined-summary"
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
                                domain_query,
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
            while len(results) > 0:
                for result in results:
                    output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"dumping of '{es_index}' data completed in {time.time() - start_time:.2f} seconds.")

            return output_list
        else:
            logger.warning('could not connect to Elasticsearch')
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

    def filter_top_active_posts(self, es_results, top_n):
        unique_results = []

        thread_dict = {}  # maps post titles to their respective activity levels
        # create dictionary with title as key and thread count as value
        for result in es_results:
            title = result['_source']['title']
            counts, contributors = self.es_fetch_contributors_and_threads(
                es_index=result['_index'],
                title=title,
                domain=result['_source']['domain']
            )
            result['_source']['n_threads'] = counts
            # exclude the post authors
            for author in result['_source']['authors']:
                contributors.remove(author)
            result['_source']['n_threads'] = counts
            result['_source']['contributors'] = contributors

            # add counts as value to thread_dict with a key as title
            thread_dict[title] = counts

        # Use the dictionary created above to sort the results
        # posts with a higher thread count are placed at the top
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

    def fetch_raw_data_for_url_with_empty_summary(self, es_index, url, start_date_str=None, end_date_str=None):
        logger.info(f"fetching all the data for url: {url}")
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

            scroll_response = self._es_client.search(
                index=es_index, body=query, size=self._es_data_fetch_size, scroll='5m'
            )
            scroll_id = scroll_response['_scroll_id']
            results = scroll_response['hits']['hits']

            logger.info(f"Starting dumping of {es_index} data in json...")
            while len(results) > 0:
                for result in results:
                    raw_output_list.append(result)

                # Fetch the next batch of results
                scroll_response = self._es_client.scroll(scroll_id=scroll_id, scroll='5m')
                scroll_id = scroll_response['_scroll_id']
                results = scroll_response['hits']['hits']

            logger.info(
                f"Dumping of {es_index} data in json has completed and has taken {time.time() - start_time:.2f} seconds.")
            logger.info(f"Total threads received : {len(raw_output_list)}")
            return raw_output_list
        else:
            logger.info('Could not connect to Elasticsearch')
            return None

    def get_earliest_posts_by_title(self, es_index, url, title):
        domain_query = self.get_domain_query(url)
        query = {
            "size": 1,  # only retrieve the first (earliest) document
            "query": {
                "bool": {
                    "must": [
                        {"term": {"title.keyword": title}},
                        domain_query
                    ]
                }
            },
            "sort": [
                {"created_at": {"order": "asc"}}  # sort by creation date ascending
            ]
        }

        response = self._es_client.search(index=es_index, body=query)
        if response['hits']['hits']:
            earliest_post = response['hits']['hits'][0]  # ['_source']
            # logger.info(f"Earlier Post for this title: {earliest_post['created_at']} - {earliest_post['title']}")
        else:
            earliest_post = {}
            logger.info(f"No earliest post found for title: {title}")
        return earliest_post

    def es_fetch_contributors_and_threads(self, es_index, title, domain):
        """
        Fetches the count of threads and unique contributors for a given post based on title and domain
        """
        # The search query
        domain_query = self.get_domain_query(domain)
        query = {
            "size": 0,  # no search hits are returned, the focus is solely on the aggregations and counts
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title.keyword": title}},
                        domain_query
                    ]
                }
            },
            # count unique authors associated with the matching documents
            "aggs": {
                "authors_list": {
                    "terms": {
                        "field": "authors.keyword",
                        "size": 10000
                    }
                }
            }
        }

        response = self._es_client.search(index=es_index, body=query)
        counts = response['hits']['total']['value']
        if int(counts) > 0:
            # exclude original post
            counts = int(counts) - 1
        contributors = [author['key'] for author in response['aggregations']['authors_list']['buckets']]
        return counts, contributors

    def fetch_data_in_date_range(self, es_index, start_date, end_date, domain):
        logger.info(f"fetching documents from {start_date} to {end_date}")
        domain_query = self.get_domain_query(domain)
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "created_at": {
                                    "gte": start_date,
                                    "lte": end_date,
                                    "format": "strict_date_optional_time||epoch_millis"
                                }
                            }
                        },
                        domain_query
                    ]
                }
            }
        }

        # perform the search using the 'scan' helper to retrieve all documents matching the query
        documents = scan(client=self._es_client, query=query, index=es_index, size=self._es_data_fetch_size)
        selected_threads = [doc for doc in documents]
        logger.info(f"number of documents fetched: {len(selected_threads)}")
        return selected_threads

    def fetch_data_with_empty_summary(self, es_index, url=None, start_date_str=None, current_date_str=None):
        logger.info(f"connecting ElasticSearch to fetch the docs with no summary ... ")
        output_list = []
        start_time = time.time()

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")

            domain_query = self.get_domain_query(url)

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
                                domain_query
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
                                domain_query
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

    def get_duplicated_data_based_on_url(self, es_index, domain_url):

        if self._es_client.ping():
            logger.success("connected to the ElasticSearch")
            query = {
                "size": 0,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "term": {
                                    "domain.keyword": str(domain_url)
                                }
                            }
                        ]
                    }
                },
                "aggs": {
                    "filtered_by_domain": {
                        "filter": {
                            "term": {
                                "domain.keyword": str(domain_url)
                            }
                        },
                        "aggs": {
                            "duplicate_urls": {
                                "terms": {
                                    "field": "url.keyword",
                                    "min_doc_count": 2,
                                    "size": 1000
                                }
                            }
                        }
                    }
                }
            }

            response = self._es_client.search(index=es_index, body=query)
            duplicated_url_list = [u['key'] for u in
                                   response['aggregations']['filtered_by_domain']['duplicate_urls']['buckets']]
            return duplicated_url_list

    def get_data_based_on_doc_url(self, es_index, doc_url):
        if self._es_client.ping():
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "term": {
                                    "url.keyword": str(doc_url)
                                }
                            }
                        ]
                    }
                }
            }

            scroll_response = self._es_client.search(
                index=es_index, body=query, size=self._es_data_fetch_size, scroll='5m'
            )
            res = scroll_response['hits']['hits']
            return res
        else:
            return []

    def document_add(self, index_name, doc, doc_id=None):
        """Funtion to add a document by providing index_name,
        document type, document contents as doc and document id."""
        resp = self._es_client.index(index=index_name, body=doc, id=doc_id)
        return resp

    def document_view(self, index_name, doc_id):
        """Function to view document."""
        try:
            resp = self._es_client.get(index=index_name, id=doc_id)
        except NotFoundError:
            resp = False
        return resp

    def document_update(self, index_name, doc_id, doc=None, new=None):
        """Function to edit a document either updating existing fields or adding a new field."""
        if doc:
            resp = self._es_client.index(index=index_name, id=doc_id, body=doc)
        else:
            resp = self._es_client.update(index=index_name, id=doc_id, body={"doc": new})
        return resp

    def document_delete(self, index_name, doc_id):
        """Function to delete a specific document."""
        resp = self._es_client.delete(index=index_name, id=doc_id)
        return resp
