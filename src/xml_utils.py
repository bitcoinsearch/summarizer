import glob
import os
import platform
import re
import shutil
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd
import pytz
from feedgen.feed import FeedGenerator
from loguru import logger
from tqdm import tqdm

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.gpt_utils import create_summary
from src.utils import preprocess_email, month_dict, get_id, clean_title, convert_to_tuple, create_folder, \
    remove_multiple_whitespaces, add_utc_if_not_present

elastic_search = ElasticSearchClient()


def get_base_directory(url):
    """
    Determine the base directory for storing files based on the provided URL.

    Args:
        url (str): The URL used to determine the base directory.

    Returns:
        str: The base directory determined based on the URL. Possible values are "bitcoin-dev", "lightning-dev", "delvingbitcoin", or "others".

    """
    if "bitcoin-dev" in url or "bitcoindev" in url:
        directory = "bitcoin-dev"
    elif "lightning-dev" in url:
        directory = "lightning-dev"
    elif "delvingbitcoin" in url:
        directory = "delvingbitcoin"
    else:
        directory = "others"
    return directory


class XMLReader:

    def get_xml_summary(self, data, dev_name):
        """
        Retrieve the summary from an XML file associated with the provided data.

        Args:
            self: The instance of the class invoking the method.
            data (dict): A dictionary containing data from a source, expected to have keys '_source', 'id', 'title', and 'created_at'.
            dev_name (str): The name of the development platform associated with the data.

        Returns:
            str or None: The summary extracted from the XML file, or None if no summary is found.

        Notes:
            This method assumes the availability of the functions get_id, clean_title, get_base_directory, and month_dict.
            It also assumes the existence of the os, pytz, and ET modules for file operations, datetime handling, and XML parsing, respectively.

        """
        number = get_id(data["_source"]["id"])
        title = data["_source"]["title"]
        xml_name = clean_title(title)
        published_at = datetime.strptime(data['_source']['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        published_at = pytz.UTC.localize(published_at)
        month_name = month_dict[int(published_at.month)]
        str_month_year = f"{month_name}_{int(published_at.year)}"
        current_directory = os.getcwd()
        directory = get_base_directory(dev_name)
        file_path = f"static/{directory}/{str_month_year}/{number}_{xml_name}.xml"
        full_path = os.path.join(current_directory, file_path)

        try:
            if os.path.exists(full_path):
                namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
                tree = ET.parse(full_path)
                root = tree.getroot()
                summ_list = root.findall(".//atom:entry/atom:summary", namespaces)
                if summ_list:
                    summ = "\n".join([summ.text for summ in summ_list])
                    return summ
                else:
                    logger.warning(f"No summary found: {full_path}")
                    return None
            else:
                # logger.warning(f"No xml file found: {full_path}")
                return None
        except Exception as e:
            logger.error(
                f"Error: {e} \n{traceback.format_exc()} \n\nFILE PATH: {full_path}\nDOC ID: {data['_source']['id']}")
            return None

    def read_xml_file(self, full_path):
        """
        Read and extract information from an XML file located at the specified path.

        Args:
            self: The instance of the class invoking the method.
            full_path (str): The path to the XML file.

        Returns:
            dict: A dictionary containing extracted information from the XML file, including 'id', 'title', 'summary',
                  'body', 'url', 'authors', 'created_at', 'body_type', 'type', 'domain', and 'indexed_at'.

        Notes:
            This method assumes the availability of the clean_title function.
            It also assumes the existence of the os, datetime, and ET modules for file operations, datetime handling, and XML parsing, respectively.

        """
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        tree = ET.parse(full_path)
        root = tree.getroot()
        title = root.findall(".//atom:entry/atom:title", namespaces)[0].text
        title_for_id = title.replace('Combined summary - ', '')
        id = 'combined_' + clean_title(title_for_id)
        summary = root.findall(".//atom:entry/atom:summary", namespaces)[0].text
        published = root.findall(".//atom:entry/atom:published", namespaces)[0].text
        # published = add_utc_if_not_present(published)
        indexed_at = ((datetime.now(timezone.utc)).replace(microsecond=0)).isoformat()
        authors = root.findall('atom:author/atom:name', namespaces)
        author_list = [author.text for author in authors]

        link = root.findall(".//atom:entry/atom:link", namespaces)[0].get('href')
        if "bitcoin-dev" in link:
            domain = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"
        elif "bitcoindev" in link:
            domain = "https://gnusha.org/pi/bitcoindev/"
        elif "lightning-dev" in link:
            domain = "https://lists.linuxfoundation.org/pipermail/lightning-dev/"
        elif "delvingbitcoin" in link:
            domain = "https://delvingbitcoin.org/"
        else:
            domain = None

        return {
            'id': id if id else None,
            'title': title if title else None,
            'summary': summary if summary else None,
            'body': summary if summary else None,
            'url': link if link else None,
            'authors': author_list if author_list else None,
            'created_at': published if published else None,
            'body_type': "raw",
            'type': "combined-summary",
            'domain': domain if domain else None,
            'indexed_at': indexed_at if indexed_at else None
        }


class GenerateXML:

    def generate_xml(self, feed_data, xml_file):
        """
        Generate an Atom XML feed based on the provided feed data and write it to the specified XML file.

        Args:
            self: The instance of the class invoking the method.
            feed_data (dict): A dictionary containing data for generating the feed, including 'id', 'title', 'authors', 'links',
                              'url', 'created_at', and 'summary'.
            xml_file (str): The path to the XML file where the generated feed will be written.

        Returns:
            None

        Notes:
            This method assumes the existence of the FeedGenerator module for generating the feed XML.

        """
        # create feed generator
        fg = FeedGenerator()
        fg.id(feed_data['id'])
        fg.title(feed_data['title'])
        for author in feed_data['authors']:
            fg.author({'name': author})
        for link in feed_data['links']:
            fg.link(href=link, rel='alternate')
        # add entries to the feed
        fe = fg.add_entry()
        fe.id(feed_data['id'])
        fe.title(feed_data['title'])
        fe.link(href=feed_data['url'], rel='alternate')
        fe.published(feed_data['created_at'])
        fe.summary(feed_data['summary'])

        # generate the feed XML
        feed_xml = fg.atom_str(pretty=True)
        with open(xml_file, 'wb') as f:
            f.write(feed_xml)

    def append_columns(self, df_dict, file, title, namespace):
        """
        Append specific information from the given XML file corresponding to a single post or reply within a thread
        to the given dictionary (df_dict).

        Args:
            self: The instance of the class invoking the method.
            df_dict (dict): A dictionary containing columns as keys and lists as values, representing DataFrame columns.
            file (str): The path to the XML file.
            title (str): The title of the post or reply.
            namespace (dict): A dictionary containing XML namespace mappings.

        Returns:
            None

        Notes:
            This method assumes the existence of the ET module for XML parsing.
            It also assumes the availability of the add_utc_if_not_present function and the re module for datetime handling and string manipulation, respectively.

        """
        # Append default values for columns that will not be directly filled from the XML
        df_dict["body_type"].append(0)
        df_dict["id"].append(file.split("/")[-1].split("_")[0])
        df_dict["type"].append(0)
        df_dict["_index"].append(0)
        df_dict["_id"].append(0)
        df_dict["_score"].append(0)

        # The title is directly provided as a parameter
        df_dict["title"].append(title)

        # Parse the XML file to extract and append relevant data
        tree = ET.parse(file)
        root = tree.getroot()

        # Extract and format the publication date
        date = root.find('atom:entry/atom:published', namespace).text
        datetime_obj = add_utc_if_not_present(date, iso_format=False)
        df_dict["created_at"].append(datetime_obj)

        # Extract the URL from the 'link' element
        link_element = root.find('atom:entry/atom:link', namespace)
        link_href = link_element.get('href')
        df_dict["url"].append(link_href)

        # Process and append the author's name, removing digits and unnecessary characters
        author = root.find('atom:author/atom:name', namespace).text
        author_result = re.sub(r"\d", "", author)
        author_result = author_result.replace(":", "")
        author_result = author_result.replace("-", "")
        df_dict["authors"].append([author_result.strip()])

    def file_not_present_df(self, columns, source_cols, df_dict, files_list, dict_data, data,
                            title, namespace):
        """
        Processes data directly from the given document (`data`) as no XML summary is
        available for that document. Also, for each individual summary (XML file) that
        already exists for the given thread, extracts and appends its content to the dictionary.
        """
        # Append basic data from dict_data for each column into df_dict using list comprehension
        for col in columns:
            df_dict[col].append(dict_data[data][col])

        # Processing source_cols with conditional append
        for col in source_cols:
            value = dict_data[data]['_source'][col]
            if "created_at" in col:
                value = add_utc_if_not_present(value, iso_format=False)
            df_dict[col].append(value)

        # Iterate over files with transformed file paths
        files_list = [file.replace("\\", "/") for file in files_list]

        # Use dictionary to store parsed XML trees to avoid redundant parsing
        parsed_files = {}

        # For each individual summary (XML file) that exists for the
        # given thread, extract and append their content to the dictionary
        for file in files_list:
            if os.path.exists(file):
                if file not in parsed_files:
                    tree = ET.parse(file)
                    root = tree.getroot()
                    parsed_files[file] = (tree, root)

                tree, root = parsed_files[file]
                file_title = root.find('atom:entry/atom:title', namespace).text

                if title == file_title:
                    self.append_columns(df_dict, file, title, namespace)

                    summary = root.find('atom:entry/atom:summary', namespace).text
                    df_dict["body"].append(summary)
            else:
                logger.info(f"file not present: {file}")

    def file_present_df(self, files_list, namespace, combined_filename, title, individual_summaries_xmls_list, df_dict):
        """
        Iterates through the list of XML files, identifying the combined XML file and
        individual summaries relevant to the given thread (as specified by title).
        It copies the combined XML file to all relevant month folders. If no combined
        summary exists, it extracts the content of individual summaries, appending it
        to the data dictionary.
        """
        # List to keep track of the month folders that contain
        # the XML files for the posts of the current thread
        month_folders = set()

        # Cached listdir calls to avoid repeated disk access
        folder_contents = {}

        # Identifying combined file and processing individual summaries in a single loop
        combined_file_fullpath = None

        for file in files_list:
            normalized_file = file.replace("\\", "/")
            # Check if the current file is the combined XML file for the thread
            if combined_filename in normalized_file:
                combined_file_fullpath = normalized_file
            # Parse the XML file to find the title and compare it with the current title
            # in order to understand if the post/file is part of the current thread
            tree = ET.parse(normalized_file)
            root = tree.getroot()
            file_title = root.find('atom:entry/atom:title', namespace).text
            # If titles match, add the file to the list of relevant XMLs and track its month folder
            if title == file_title:
                individual_summaries_xmls_list.append(normalized_file)
                month_folder_path = "/".join(normalized_file.split("/")[:-1])
                month_folders.add(month_folder_path)

        # Ensure the combined XML file is copied to all relevant month folders
        for month_folder in month_folders:
            if month_folder not in folder_contents:
                folder_contents[month_folder] = os.listdir(month_folder)

            if combined_file_fullpath and combined_filename not in folder_contents[month_folder]:
                shutil.copy(combined_file_fullpath, month_folder)

        # If individual summaries exist but no combined summary,
        # extract and append their content to the dictionary
        combined_exists = any(combined_filename in item for item in files_list)
        if individual_summaries_xmls_list and not combined_exists:
            logger.info("Individual summaries are present but not combined ones.")
            for file in individual_summaries_xmls_list:
                self.append_columns(df_dict, file, title, namespace)
                tree = ET.parse(file)
                root = tree.getroot()
                summary = root.find('atom:entry/atom:summary', namespace).text
                df_dict["body"].append(summary)

    def preprocess_authors_name(self, author_tuple):
        """
        Preprocess author names by removing '+' characters and stripping whitespace.

        Args:
            self: The instance of the class invoking the method.
            author_tuple (tuple): A tuple containing author names.

        Returns:
            tuple: A tuple with author names processed by removing '+' characters and stripping whitespace.

        Notes:
            This method assumes that author names are provided as a tuple of strings.

        """
        author_tuple = tuple(s.replace('+', '').strip() for s in author_tuple)
        return author_tuple

    def get_local_xml_file_paths(self, dev_url):
        """
        Retrieve paths for all relevant local XML files based on the given domain.

        Args:
            self: The instance of the class invoking the method.
            dev_url (str): The URL of the development platform.

        Returns:
            list: A list containing paths to relevant local XML files.

        Notes:
            This method assumes the existence of the os and glob modules for file operations.
            It also assumes the availability of the get_base_directory function.

        """
        current_directory = os.getcwd()
        directory = get_base_directory(dev_url)
        files_list = glob.glob(os.path.join(current_directory, "static", directory, "**/*.xml"), recursive=True)
        return files_list

    def get_local_xml_file_paths_for_title(self, dev_url, title):
        """
        Retrieve paths for all relevant local XML files based on the given domain and title.

        Args:
            self: The instance of the class invoking the method.
            dev_url (str): The URL of the development platform.
            title (str): The title of the post or reply.

        Returns:
            list: A list containing paths to relevant local XML files.

        """
        current_directory = os.getcwd()
        directory = get_base_directory(dev_url)
        files_list = glob.glob(os.path.join(current_directory, "static", directory, f"**/*{title}.xml"), recursive=True)
        return files_list

    def generate_new_emails_df(self, main_dict_data, dev_url):
        """
        Generate a new DataFrame containing email data from the given main dictionary data and development URL.

        Args:
            self: The instance of the class invoking the method.
            main_dict_data (list): A list of dictionaries containing data fetched from Elasticsearch Index.
            dev_url (str): The URL of the development platform.

        Returns:
            pandas.DataFrame: A DataFrame containing email data extracted from the main dictionary data.

        Notes:
            This method assumes the existence of the elastic_search module for fetching data based on title.
            It also assumes the availability of the get_id, clean_title, get_local_xml_file_paths_for_title, and logger functions,
            as well as the preprocess_authors_name, remove_multiple_whitespaces, and preprocess_email functions.

        """
        # Define XML namespace for parsing XML files
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}

        # Initialize a dictionary to store data for DataFrame construction, with predefined columns
        columns = ['_index', '_id', '_score']
        source_cols = ['body_type', 'created_at', 'id', 'title', 'body', 'type',
                       'url', 'authors']
        df_dict = {col: [] for col in (columns + source_cols)}

        seen_titles = set()
        # Process each document in the input data
        for idx in range(len(main_dict_data)):
            xmls_list = []  # the existing XML files for the thread that the fetched document is part of
            thread_title = main_dict_data[idx]["_source"]["title"]
            if thread_title in seen_titles:
                continue

            # `files_list` contains all existing XML files for the current thread
            # but older threads might lack corresponding XML files if they were
            # inactive when we began creating summaries. When such threads become
            # active, XML files for their posts/docs are absent.
            # To address this, we fetch all documents under the active thread to
            # prepare for XML generation in subsequent processing steps.
            title_dict_data = elastic_search.fetch_data_based_on_title(
                es_index=ES_INDEX, title=thread_title, url=dev_url
            )
            for data_idx in range(len(title_dict_data)):
                # Extract relevant identifiers and metadata from the document
                title = title_dict_data[data_idx]["_source"]["title"]
                number = get_id(title_dict_data[data_idx]["_source"]["id"])
                xml_name = clean_title(title)
                file_name = f"{number}_{xml_name}.xml"
                combined_filename = f"combined_{xml_name}.xml"
                created_at = title_dict_data[data_idx]["_source"]["created_at"]

                # Retrieve all existing XML files (summaries) for the given source and title
                files_list = self.get_local_xml_file_paths_for_title(dev_url=dev_url, title=xml_name)

                # Check if the XML file for the document exists
                if not any(file_name in item for item in files_list):
                    logger.info(f"Not present: {created_at} | {file_name}")
                    self.file_not_present_df(columns, source_cols, df_dict, files_list, title_dict_data, data_idx,
                                             title, namespaces)
                else:
                    logger.info(f"Present: {created_at} | {file_name}")
                    self.file_present_df(files_list, namespaces, combined_filename, title, xmls_list, df_dict)

                seen_titles.add(thread_title)

        # Convert the dictionary to a pandas DataFrame for structured data representation
        emails_df = pd.DataFrame(df_dict)
        # Clean and preprocess fields in the DataFrame
        emails_df['authors'] = emails_df['authors'].apply(convert_to_tuple)
        emails_df = emails_df.drop_duplicates()
        emails_df['authors'] = emails_df['authors'].apply(self.preprocess_authors_name)
        emails_df['body'] = emails_df['body'].apply(preprocess_email)
        emails_df['title'] = emails_df['title'].apply(remove_multiple_whitespaces)
        # logger.info(f"Shape of emails_df: {emails_df.shape}")
        return emails_df

    def start(self, dict_data, url):
        """
        Start the process of generating local XML files and combined summaries based on the provided dictionary data and URL.

        Args:
            self: The instance of the class invoking the method.
            dict_data (list): A list of dictionaries containing data fetched from Elasticsearch Index.
            url (str): The URL of the development platform.

        Returns:
            None

        Notes:
            This method assumes the existence of the logger object, the get_id, clean_title, convert_to_tuple, preprocess_authors_name,
            generate_new_emails_df, generate_local_xml, create_summary, get_base_directory, add_utc_if_not_present, and generate_xml functions,
            as well as the month_dict object.
            It also assumes the availability of the os, platform, pandas, shutil, and tqdm modules for file operations, platform information,
            DataFrame manipulation, file copying, and progress tracking, respectively.

        """
        if len(dict_data) > 0:
            emails_df = self.generate_new_emails_df(dict_data, url)
            if len(emails_df) > 0:
                emails_df['created_at_org'] = emails_df['created_at'].astype(str)

                def generate_local_xml(cols, combine_flag, url):
                    """
                    Generate a local XML file based on the provided columns data, combine flag, and URL.

                    Args:
                        cols (dict): A dictionary containing column data, including 'id', 'created_at', 'title', 'body', 'authors', and 'url'.
                        combine_flag (str): A flag indicating whether to combine the XML file with others.
                        url (str): The URL of the development platform.

                    Returns:
                        str: The file path of the generated local XML file.

                    Notes:
                        This method assumes the existence of the add_utc_if_not_present, create_folder, get_id, clean_title,
                        get_base_directory, create_summary, and generate_xml functions, as well as the month_dict and logger objects.

                    """
                    if isinstance(cols['created_at'], str):
                        cols['created_at'] = add_utc_if_not_present(cols['created_at'], iso_format=False)
                    month_name = month_dict[int(cols['created_at'].month)]
                    str_month_year = f"{month_name}_{int(cols['created_at'].year)}"
                    number = get_id(cols['id'])
                    xml_name = clean_title(cols['title'])

                    directory = get_base_directory(url)
                    dir_path = f"static/{directory}/{str_month_year}"

                    # create directory if it doesn't exist
                    if not os.path.exists(dir_path):
                        create_folder(dir_path)

                    # construct a file path
                    file_path = f"{dir_path}/{number}_{xml_name}.xml"

                    # Check if we already created a summary for this post in the past
                    if os.path.exists(file_path):
                        # if XML file exists, we already created a summary
                        logger.info(f"Exist: {file_path}")
                        return fr"{directory}/{str_month_year}/{number}_{xml_name}.xml"

                    # No summary was found, we need to create one
                    logger.info(f"Not found: {file_path}")
                    summary = create_summary(cols['body'])
                    feed_data = {
                        'id': combine_flag,
                        'title': cols['title'],
                        'authors': [f"{cols['authors'][0]} {cols['created_at']}"],
                        'url': cols['url'],
                        'links': [],
                        'created_at': cols['created_at_org'],
                        'summary': summary
                    }
                    self.generate_xml(feed_data, file_path)
                    return fr"{directory}/{str_month_year}/{number}_{xml_name}.xml"

                os_name = platform.system()
                # logger.info(f"Operating System: {os_name}")

                # Identify threads by getting unique titles across posts
                titles = emails_df.sort_values('created_at')['title'].unique()
                logger.info(f"Total titles in data: {len(titles)}")
                for title_idx, title in tqdm(enumerate(titles)):
                    # Filter emails by title and prepare them for XML generation
                    title_df = emails_df[emails_df['title'] == title]
                    title_df['authors'] = title_df['authors'].apply(convert_to_tuple)
                    title_df = title_df.drop_duplicates()
                    title_df['authors'] = title_df['authors'].apply(self.preprocess_authors_name)
                    title_df = title_df.sort_values(by='created_at', ascending=False)
                    logger.info(f"Number of docs for title: {title}: {len(title_df)}")

                    # Handle threads with single and multiple documents differently
                    if len(title_df) < 1:
                        continue
                    if len(title_df) == 1:
                        # Don't create combined summary for threads with no replies
                        generate_local_xml(title_df.iloc[0], "0", url)
                        continue
                    # COMBINED SUMMARY GENERATION
                    # Combine the individual posts of the thread into combined_body
                    combined_body = '\n\n'.join(title_df['body'].apply(str))
                    xml_name = clean_title(title)
                    # Generate XML files (if not exist) for each post in the thread, collecting their paths into combined_links
                    combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1))
                    # Generate a list of strings, each combining the first author's name with their post's creation date
                    combined_authors = list(
                        title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1))
                    # Group emails by month and year based on their creation date to process them in time-based segments
                    month_year_group = \
                        title_df.groupby([title_df['created_at'].dt.month, title_df['created_at'].dt.year])

                    flag = False
                    std_file_path = ""
                    for idx, (month_year, _) in enumerate(month_year_group):
                        # logger.info(f"Month and Year: {month_year}")
                        month_name = month_dict[int(month_year[0])]
                        str_month_year = f"{month_name}_{month_year[1]}"

                        directory = get_base_directory(url)
                        file_path = fr"static/{directory}/{str_month_year}/combined_{xml_name}.xml"
                        # Generate a single combined thread summary using:
                        # - the individual summaries of previous posts
                        # - the actual content of newer posts
                        combined_summary = create_summary(combined_body)
                        feed_data = {
                            'id': "2",
                            'title': 'Combined summary - ' + title,
                            'authors': combined_authors,
                            'url': title_df.iloc[0]['url'],
                            'links': combined_links,
                            'created_at': add_utc_if_not_present(title_df.iloc[0]['created_at_org']),
                            'summary': combined_summary
                        }
                        # We use a flag to check if the XML file for the
                        # combined summary is generated for the first time
                        if not flag:
                            # Generate XML only once for the first month-year and keep its path
                            self.generate_xml(feed_data, file_path)
                            std_file_path = file_path
                            flag = True
                        else:
                            # For subsequent month-year groups, copy the initially
                            # created XML file instead of creating a new one
                            if os_name == "Windows":
                                shutil.copy(std_file_path, file_path)
                            elif os_name == "Linux":
                                os.system(f"cp {std_file_path} {file_path}")
            else:
                logger.info(f"No new files are found for: {url}")
        else:
            logger.info(f"No input data found for: {url}")
