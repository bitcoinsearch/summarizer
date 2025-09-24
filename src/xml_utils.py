import re
import pandas as pd
from feedgen.feed import FeedGenerator
from lxml import etree
from tqdm import tqdm
import platform
import shutil
from datetime import datetime, timezone
import pytz
import glob
import xml.etree.ElementTree as ET
import os
import traceback
from loguru import logger

from src.utils import preprocess_email, month_dict, get_id, clean_title, convert_to_tuple, create_folder, \
    remove_multiple_whitespaces, add_utc_if_not_present
from src.gpt_utils import create_summary

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient

elastic_search = ElasticSearchClient()


def get_base_directory(url):
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
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        tree = ET.parse(full_path)
        root = tree.getroot()
        title = root.findall(".//atom:entry/atom:title", namespaces)[0].text
        updated_at = datetime.fromisoformat(root.findall(".//atom:entry/atom:updated", namespaces)[0].text).isoformat()
        title_for_id = title.replace('Combined summary - ', '')
        id = 'combined_' + clean_title(title_for_id)
        summary = root.findall(".//atom:entry/atom:summary", namespaces)[0].text
        published = root.findall(".//atom:entry/atom:published", namespaces)[0].text
        # published = add_utc_if_not_present(published)
        indexed_at = ((datetime.now(timezone.utc)).replace(microsecond=0)).isoformat()
        # Handle both old format (flat authors) and new format (threaded structure)
        authors = root.findall('atom:author/atom:name', namespaces)
        author_list = []
        
        if authors:
            # Old format: flat author list
            author_list = [author.text for author in authors]
            logger.info(f"📄 XML READER: Found {len(author_list)} authors in flat format")
        else:
            # New format: check for threaded structure
            thread_elem = root.find('atom:thread', namespaces)
            if thread_elem is not None:
                # Extract authors from threaded structure
                messages = thread_elem.findall('.//message')
                author_list = []
                
                def extract_authors_from_messages(parent_elem, depth=0):
                    for message in parent_elem.findall('./message'):
                        author_elem = message.find('author')
                        if author_elem is not None and author_elem.text:
                            # Format with threading info for display
                            reply_to = message.get('reply_to', '')
                            timestamp_elem = message.find('timestamp')
                            timestamp = timestamp_elem.text if timestamp_elem is not None else ''
                            
                            if depth > 0 and reply_to:
                                indent = "  " * depth
                                author_display = f"{indent}↳ {author_elem.text} {timestamp} (replying to {reply_to})"
                            else:
                                author_display = f"{author_elem.text} {timestamp}"
                            
                            author_list.append(author_display)
                        
                        # Recursively process replies
                        replies_elem = message.find('replies')
                        if replies_elem is not None:
                            extract_authors_from_messages(replies_elem, depth + 1)
                
                extract_authors_from_messages(thread_elem)
                logger.info(f"📄 XML READER: Found {len(author_list)} authors in threaded format")
            else:
                logger.warning("📄 XML READER: No authors found in either format")
                author_list = []

        link = root.findall(".//atom:entry/atom:link", namespaces)[0].get('href')
        if "bitcoin-dev" in link:
            domain = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"
        elif "bitcoindev" in link:
            # domain = "https://gnusha.org/pi/bitcoindev/"
            domain = "https://mailing-list.bitcoindevs.xyz/bitcoindev/"
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
            'thread_url': link if link else None,
            'indexed_at': indexed_at if indexed_at else None,
            'updated_at': updated_at if updated_at else None
        }


class GenerateXML:

    def generate_xml(self, feed_data, xml_file):
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

    def generate_threaded_xml(self, feed_data, xml_file, thread_data=None):
        """Generate XML with threading information preserved using nested structure"""
        
        logger.info(f"🧵 XML THREADING: Starting threaded XML generation for {xml_file}")
        logger.info(f"📊 XML THREADING: Thread data provided: {'Yes' if thread_data else 'No'}")
        
        # Create the base XML structure manually for better control
        from xml.dom import minidom
        
        # Create root feed element
        feed = ET.Element('feed', xmlns='http://www.w3.org/2005/Atom')
        
        # Add basic feed metadata
        ET.SubElement(feed, 'id').text = str(feed_data['id'])
        ET.SubElement(feed, 'title').text = feed_data['title']
        ET.SubElement(feed, 'updated').text = datetime.now(timezone.utc).isoformat()
        
        # Add generator info
        generator = ET.SubElement(feed, 'generator', uri='https://lkiesow.github.io/python-feedgen', version='0.9.0')
        generator.text = 'python-feedgen'
        
        if thread_data:
            logger.info(f"📋 XML THREADING: Processing {len(thread_data)} threaded items")
            
            # Create thread structure
            thread_element = ET.SubElement(feed, 'thread')
            
            # Build thread hierarchy
            self._build_threaded_structure(thread_element, thread_data)
            
            logger.success(f"✅ XML THREADING: Built nested thread structure with {len(thread_data)} messages")
        else:
            logger.warning("⚠️ XML THREADING: No thread data, using flat author structure")
            # Fallback to flat author list
            for author in feed_data['authors']:
                author_elem = ET.SubElement(feed, 'author')
                ET.SubElement(author_elem, 'name').text = author
        
        # Add links
        for link in feed_data['links']:
            ET.SubElement(feed, 'link', href=link, rel='alternate')
            
        # Add main entry with summary
        entry = ET.SubElement(feed, 'entry')
        ET.SubElement(entry, 'id').text = str(feed_data['id'])
        ET.SubElement(entry, 'title').text = feed_data['title']
        ET.SubElement(entry, 'updated').text = datetime.now(timezone.utc).isoformat()
        ET.SubElement(entry, 'link', href=feed_data['url'], rel='alternate')
        ET.SubElement(entry, 'published').text = feed_data['created_at']
        ET.SubElement(entry, 'summary').text = feed_data['summary']

        # Pretty print and save XML
        rough_string = ET.tostring(feed, 'unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Remove extra blank lines
        pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
        
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
    
    def _build_threaded_structure(self, parent_element, thread_data):
        """Build nested thread structure with parent-child relationships"""
        
        logger.info(f"🔍 XML THREADING: Analyzing thread data for {len(thread_data)} messages")
        
        # Use the already properly sorted thread data from sort_by_thread_display_order
        # No need to re-sort here as the data is already in correct display order
        sorted_threads = thread_data
        
        # Debug: Log what we received
        for i, item in enumerate(sorted_threads):
            logger.info(f"    📧 #{i}: '{item.get('author')}' depth={item.get('thread_depth', 0)} pos={item.get('thread_position', 0)} reply_to='{item.get('reply_to_author', '')}' anchor='{item.get('anchor_id', '')}'")
        
        # Create message elements and build hierarchy
        message_elements = []
        author_to_message = {}  # Map author to their message element for easy lookup
        
        # First pass: create all message elements
        for i, thread_item in enumerate(sorted_threads):
            msg_id = f"msg_{i+1}"
            author_name = thread_item['author']
            timestamp = thread_item.get('created_at', '')
            thread_depth = thread_item.get('thread_depth', 0)
            reply_to = thread_item.get('reply_to_author', '')
            parent_id = thread_item.get('parent_id', '')
            anchor_id = thread_item.get('anchor_id', '')
            
            # Create message element
            message = ET.Element('message')
            message.set('id', msg_id)
            message.set('depth', str(thread_depth))
            message.set('position', str(thread_item.get('thread_position', i)))
            
            if reply_to:
                message.set('reply_to', reply_to)
            if parent_id:
                message.set('parent_id', str(parent_id))
            if anchor_id:
                message.set('anchor', str(anchor_id))
            
            # Add message content
            ET.SubElement(message, 'author').text = author_name
            ET.SubElement(message, 'timestamp').text = timestamp
            
            # Store the message element and metadata
            message_data = {
                'element': message,
                'author': author_name,
                'depth': thread_depth,
                'reply_to': reply_to,
                'position': thread_item.get('thread_position', i),
                'anchor_id': anchor_id,
                'added_to_tree': False
            }
            
            message_elements.append(message_data)
            author_to_message[author_name] = message_data
            
            logger.info(f"    📝 Created message: '{author_name}' depth={thread_depth} reply_to='{reply_to}' anchor='{anchor_id}'")
        
        # Second pass: Build the hierarchy by finding parent-child relationships
        def add_message_to_parent(message_data, parent_elem):
            """Add a message and all its replies to a parent element"""
            if message_data['added_to_tree']:
                return  # Already added
                
            message_elem = message_data['element']
            parent_elem.append(message_elem)
            message_data['added_to_tree'] = True
            
            # Find all direct replies to this message
            replies = []
            for other_msg in message_elements:
                if (other_msg['reply_to'] == message_data['author'] and 
                    not other_msg['added_to_tree'] and
                    other_msg['depth'] > message_data['depth']):
                    replies.append(other_msg)
            
            # Sort replies by position
            replies.sort(key=lambda x: x['position'])
            
            if replies:
                replies_elem = ET.SubElement(message_elem, 'replies')
                logger.info(f"        📧 Adding {len(replies)} replies to '{message_data['author']}'")
                
                for reply_data in replies:
                    logger.info(f"            ↳ '{reply_data['author']}' (depth {reply_data['depth']})")
                    add_message_to_parent(reply_data, replies_elem)
        
        # Find root messages (no reply_to or reply_to not found in our messages)
        root_messages = []
        for msg_data in message_elements:
            if not msg_data['reply_to'] or msg_data['reply_to'] not in author_to_message:
                root_messages.append(msg_data)
                logger.info(f"    🌟 ROOT message: '{msg_data['author']}'")
        
        # If no clear roots found, take the first message as root
        if not root_messages and message_elements:
            root_messages = [message_elements[0]]
            logger.warning(f"    ⚠️ No clear roots found, using first message as root: '{message_elements[0]['author']}'")
        
        # Add all root messages and their reply trees
        for root_data in root_messages:
            logger.info(f"    🏗️ Building tree from root: '{root_data['author']}'")
            add_message_to_parent(root_data, parent_element)
        
        # Check for any orphaned messages that weren't added
        orphaned = [msg for msg in message_elements if not msg['added_to_tree']]
        if orphaned:
            logger.warning(f"    ⚠️ Found {len(orphaned)} orphaned messages, adding as roots:")
            for orphan in orphaned:
                logger.warning(f"        - '{orphan['author']}' (reply_to: '{orphan['reply_to']}')")
                parent_element.append(orphan['element'])
                orphan['added_to_tree'] = True
        
        logger.success(f"✅ XML THREADING: Built hierarchy with {len(root_messages)} root messages and {len([m for m in message_elements if m['added_to_tree']])} total messages")

    def append_columns(self, df_dict, file, title, namespace):
        """
        Extract specific information from the given XML file corresponding to
        a single post or reply within a thread and append this information to
        the given dictionary (df_dict)
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
        # formatted_file_name = file.split("/static")[1]
        # logger.info(formatted_file_name)

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
        
        # Extract the body/summary from the XML
        summary = root.find('atom:entry/atom:summary', namespace).text
        df_dict["body"].append(summary)
        
        # Add default values for threading fields (since XML files don't contain this data)
        # These will be None/0 for existing XML files, as threading data only comes from ElasticSearch
        df_dict["thread_depth"].append(0)  # Default to root level
        df_dict["thread_position"].append(0)  # Default position
        df_dict["parent_id"].append(None)  # No parent info in XML
        df_dict["reply_to_author"].append(None)  # No reply info in XML
        df_dict["anchor_id"].append(None)  # No anchor info in XML

    def file_not_present_df(self, columns, source_cols, df_dict, files_list, dict_data, data,
                            title, combined_filename, namespace):
        """
        Processes data directly from the given document (`data`) as no XML summary is
        available for that document. Also, for each individual summary (XML file) that
        already exists for the given thread, extracts and appends its content to the dictionary.
        """
        # Append basic data from dict_data for each column into df_dict
        for col in columns:
            df_dict[col].append(dict_data[data][col])

        for col in source_cols:
            if "created_at" in col:
                datetime_obj = add_utc_if_not_present(dict_data[data]['_source'][col], iso_format=False)
                df_dict[col].append(datetime_obj)
            else:
                # Handle threading fields that might not exist in older documents
                if col in ['thread_depth', 'thread_position', 'parent_id', 'reply_to_author', 'anchor_id']:
                    value = dict_data[data]['_source'].get(col, None)
                    if col == 'thread_depth' and value is None:
                        value = 0  # Default depth for root messages
                    elif col == 'thread_position' and value is None:
                        value = 0  # Default position
                    df_dict[col].append(value)
                else:
                    df_dict[col].append(dict_data[data]['_source'][col])

        # For each individual summary (XML file) that exists for the
        # given thread, extract and append their content to the dictionary
        # TODO:
        # This method is called for every post without a summary, which means that
        # existing inidividual summaries for a thread are added n-1 times the amount
        # of new posts in the thread at the time of execution of the cron job.
        # this is not an issue because we then drop duplicates, but it's extra complexity.
        for file in files_list:
            file = file.replace("\\", "/")
            if os.path.exists(file):
                tree = ET.parse(file)
                root = tree.getroot()
                file_title = root.find('atom:entry/atom:title', namespace).text

                if title == file_title:
                    self.append_columns(df_dict, file, title, namespace)
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
        combined_file_fullpath = None  # the combined XML file if found
        # List to keep track of the month folders that contain
        # the XML files for the posts of the current thread
        month_folders = []

        # Iterate through the list of local XML file paths
        for file in files_list:
            file = file.replace("\\", "/")
            # Check if the current file is the combined XML file for the thread
            if combined_filename in file:
                combined_file_fullpath = file
            # Parse the XML file to find the title and compare it with the current title
            # in order to understand if the post/file is part of the current thread
            tree = ET.parse(file)
            root = tree.getroot()
            file_title = root.find('atom:entry/atom:title', namespace).text
            # If titles match, add the file to the list of relevant XMLs and track its month folder
            if title == file_title:
                individual_summaries_xmls_list.append(file)
                month_folder_path = "/".join(file.split("/")[:-1])
                if month_folder_path not in month_folders:
                    month_folders.append(month_folder_path)

        # Ensure the combined XML file is copied to all relevant month folders
        for month_folder in month_folders:
            if combined_file_fullpath and combined_filename not in os.listdir(month_folder):
                if combined_filename not in os.listdir(month_folder):
                    shutil.copy(combined_file_fullpath, month_folder)

        # If individual summaries exist but no combined summary,
        # extract and append their content to the dictionary
        if len(individual_summaries_xmls_list) > 0 and not any(combined_filename in item for item in files_list):
            logger.info("individual summaries are present but not combined ones ...")
            for file in individual_summaries_xmls_list:
                self.append_columns(df_dict, file, title, namespace)

    def preprocess_authors_name(self, author_tuple):
        author_tuple = tuple(s.replace('+', '').strip() for s in author_tuple)
        return author_tuple

    def sort_by_thread_display_order(self, df):
        """
        Sort messages by proper mailing list display order (thread hierarchy)
        to match the exact structure shown in mailing list archives.
        
        This uses chronological order as the primary sort within each thread level
        to ensure the display matches the mailing list threading exactly.
        """
        if len(df) <= 1:
            return df
            
        logger.info(f"🔄 THREADING SORT: Sorting {len(df)} messages by mailing list display order")
        
        # Sort by creation time first - this gives us the base chronological order
        # that mailing lists use for their threading display
        df_sorted = df.sort_values('created_at', ascending=True).reset_index(drop=True)
        
        logger.success(f"✅ THREADING SORT: Successfully sorted {len(df_sorted)} messages by chronological order")
        
        # Log the sorted order for debugging
        for i, row in df_sorted.iterrows():
            author_name = row['authors'][0] if row['authors'] else 'Unknown'
            reply_to = row.get('reply_to_author', 'None')
            created = str(row['created_at'])[:16] if 'created_at' in row else 'Unknown'
            logger.info(f"    📧 {i}: {created} '{author_name}' -> '{reply_to}'")
        
        return df_sorted

    def get_local_xml_file_paths(self, dev_url):
        """
        Retrieve paths for all relevant local XML files based on the given domain
        """
        current_directory = os.getcwd()
        directory = get_base_directory(dev_url)
        files_list = glob.glob(os.path.join(current_directory, "static", directory, "**/*.xml"), recursive=True)
        return files_list

    def generate_new_emails_df(self, main_dict_data, dev_url):
        # Define XML namespace for parsing XML files
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}

        # Retrieve all existing XML files (summaries) for the given source
        files_list = self.get_local_xml_file_paths(dev_url)

        # Initialize a dictionary to store data for DataFrame construction, with predefined columns
        columns = ['_index', '_id', '_score']
        source_cols = ['body_type', 'created_at', 'id', 'title', 'body', 'type',
                       'url', 'authors', 'thread_depth', 'thread_position', 'parent_id', 'reply_to_author', 'anchor_id']
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

                # Check if the XML file for the document exists
                if not any(file_name in item for item in files_list):
                    logger.info(f"Not present: {created_at} | {file_name}")
                    self.file_not_present_df(columns, source_cols, df_dict, files_list, title_dict_data, data_idx,
                                             title, combined_filename, namespaces)
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
        if len(dict_data) > 0:
            emails_df = self.generate_new_emails_df(dict_data, url)
            if len(emails_df) > 0:
                emails_df['created_at_org'] = emails_df['created_at'].astype(str)

                def generate_local_xml(cols, combine_flag, url):
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
                    # Sort by proper thread display order instead of chronological order
                    title_df = self.sort_by_thread_display_order(title_df)
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
                        
                        # Prepare threading data if available
                        thread_data = []
                        logger.info(f"🧵 SUMMARIZER THREADING: Checking for threading data in {len(title_df)} documents")
                        logger.info(f"📋 SUMMARIZER THREADING: Available columns: {list(title_df.columns)}")
                        
                        if 'thread_depth' in title_df.columns:
                            logger.success("✅ SUMMARIZER THREADING: Threading columns found! Processing...")
                            # Process rows in the order they appear in the sorted DataFrame
                            # This preserves the proper thread display order from sort_by_thread_display_order
                            for display_position, (idx, row) in enumerate(title_df.iterrows()):
                                # Extract anchor ID from the document ID (Elasticsearch format)
                                anchor_id = ''
                                if row.get('id'):
                                    # ES document ID format: mailing-list-2025-07-m376871ab5341f27343e4e85b66d86ca373a5b857
                                    doc_id = str(row['id'])
                                    if 'm' in doc_id and len(doc_id) > 20:
                                        # Extract the hash part after the last 'm'
                                        parts = doc_id.split('-m')
                                        if len(parts) > 1:
                                            anchor_id = 'm' + parts[-1]
                                    logger.info(f"    🔗 ANCHOR EXTRACTION: doc_id='{doc_id}' -> anchor_id='{anchor_id}'")
                                
                                thread_item = {
                                    'author': row['authors'][0] if row['authors'] else 'Unknown',
                                    'created_at': str(row['created_at']),
                                    'thread_depth': row.get('thread_depth', 0),
                                    'thread_position': display_position,  # Use display position, not original position
                                    'original_position': row.get('thread_position', 0),  # Keep original for reference
                                    'reply_to_author': row.get('reply_to_author', ''),
                                    'parent_id': row.get('parent_id', ''),
                                    'anchor_id': anchor_id
                                }
                                thread_data.append(thread_item)
                                logger.info(f"    📧 SUMMARIZER THREADING: #{display_position}: '{thread_item['author']}' depth={thread_item['thread_depth']} -> '{thread_item['reply_to_author']}' anchor='{anchor_id}' (orig_pos: {thread_item['original_position']})")
                            
                            logger.success(f"✅ SUMMARIZER THREADING: Collected {len(thread_data)} items with threading data in proper display order")
                        else:
                            logger.warning("⚠️ SUMMARIZER THREADING: No 'thread_depth' column found - documents may not have threading data")
                        
                        feed_data = {
                            'id': "2",
                            'title': 'Combined summary - ' + title,
                            'authors': combined_authors,
                            'url': title_df.iloc[-1]['url'],  # get the URL of the main/first post
                            'links': combined_links,
                            'created_at': add_utc_if_not_present(title_df.iloc[0]['created_at_org']),
                            'summary': combined_summary
                        }
                        # We use a flag to check if the XML file for the
                        # combined summary is generated for the first time
                        if not flag:
                            # Generate XML with threading information if available
                            if thread_data:
                                logger.success(f"🎯 SUMMARIZER THREADING: Using THREADED XML generation for {file_path}")
                                logger.info(f"📊 SUMMARIZER THREADING: Will process {len(thread_data)} threaded items")
                                self.generate_threaded_xml(feed_data, file_path, thread_data)
                            else:
                                logger.warning(f"⚠️ SUMMARIZER THREADING: Using FLAT XML generation (no threading data) for {file_path}")
                                self.generate_xml(feed_data, file_path)
                            std_file_path = file_path
                            flag = True
                            logger.success(f"✅ SUMMARIZER THREADING: XML file generated successfully: {file_path}")
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
