import re
import pandas as pd
from feedgen.feed import FeedGenerator
from tqdm import tqdm
import platform
import shutil
from datetime import datetime, timezone
import pytz
import glob
import xml.etree.ElementTree as ET
import os
from loguru import logger

from src.utils import preprocess_email, month_dict, get_id, clean_title, convert_to_tuple, create_folder, remove_multiple_whitespaces
from src.gpt_utils import create_summary


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
        file_path = f"static/{dev_name}/{str_month_year}/{number}_{xml_name}.xml"
        full_path = os.path.join(current_directory, file_path)

        try:
            if os.path.exists(full_path):
                namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
                tree = ET.parse(full_path)
                root = tree.getroot()
                summ_list = root.findall(".//atom:entry/atom:summary", namespaces)
                if summ_list:
                    summ = "\n".join([summ.text for summ in summ_list])
                    return summ, f"Summary text found: {full_path}"
                else:
                    return None, f"No summary found: {full_path}"
            else:
                return None, f"No xml file found: {full_path}"
        except Exception as e:
            ex_message = f"Error: {e} at file path: {full_path}"
            logger.error(ex_message)
            return None, ex_message

    def read_xml_file(self, full_path):
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        tree = ET.parse(full_path)
        root = tree.getroot()
        title = root.findall(".//atom:entry/atom:title", namespaces)[0].text
        title_for_id = title.replace('Combined summary - ', '')
        id = 'combined_' + clean_title(title_for_id)
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

    def append_columns(self, df_dict, file, title, namespace):
        df_dict["body_type"].append(0)
        df_dict["id"].append(file.split("/")[-1].split("_")[0])
        df_dict["type"].append(0)
        df_dict["_index"].append(0)
        df_dict["_id"].append(0)
        df_dict["_score"].append(0)

        df_dict["title"].append(title)
        formatted_file_name = file.split("/static")[1]
        logger.info(formatted_file_name)

        tree = ET.parse(file)
        root = tree.getroot()

        date = root.find('atom:entry/atom:published', namespace).text
        datetime_obj = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00")
        timezone = pytz.UTC
        datetime_obj = datetime_obj.replace(tzinfo=timezone)
        df_dict["created_at"].append(datetime_obj)

        link_element = root.find('atom:entry/atom:link', namespace)
        link_href = link_element.get('href')
        df_dict["url"].append(link_href)

        author = root.find('atom:author/atom:name', namespace).text
        author_result = re.sub(r"\d", "", author)
        author_result = author_result.replace(":", "")
        author_result = author_result.replace("-", "")
        df_dict["authors"].append([author_result.strip()])

    def file_not_present_df(self, columns, source_cols, df_dict, files_list, dict_data, data,
                            title, combined_filename, namespace):
        for col in columns:
            df_dict[col].append(dict_data[data][col])

        for col in source_cols:
            if "created_at" in col:
                datetime_obj = datetime.strptime(dict_data[data]['_source'][col], "%Y-%m-%dT%H:%M:%S.%fZ")
                timezone = pytz.UTC
                datetime_obj = datetime_obj.replace(tzinfo=timezone)
                df_dict[col].append(datetime_obj)
            else:
                df_dict[col].append(dict_data[data]['_source'][col])
        for file in files_list:
            file = file.replace("\\", "/")
            if os.path.exists(file):
                tree = ET.parse(file)
                root = tree.getroot()
                file_title = root.find('atom:entry/atom:title', namespace).text

                if title == file_title:
                    self.append_columns(df_dict, file, title, namespace)

                    if combined_filename in file:
                        tree = ET.parse(file)
                        root = tree.getroot()
                        summary = root.find('atom:entry/atom:summary', namespace).text
                        df_dict["body"].append(summary)
                    else:
                        summary = root.find('atom:entry/atom:summary', namespace).text
                        df_dict["body"].append(summary)
            else:
                logger.info(f"File not present:- {file}")

    def file_present_df(self, files_list, namespace, combined_filename, title, xmls_list, df_dict):
        combined_file_fullpath = None
        month_folders = []
        for file in files_list:
            file = file.replace("\\", "/")
            if combined_filename in file:
                combined_file_fullpath = file
            tree = ET.parse(file)
            root = tree.getroot()
            file_title = root.find('atom:entry/atom:title', namespace).text
            if title == file_title:
                xmls_list.append(file)
                month_folder_path = "/".join(file.split("/")[:-1])
                if month_folder_path not in month_folders:
                    month_folders.append(month_folder_path)

        for month_folder in month_folders:
            if combined_file_fullpath and combined_filename not in os.listdir(month_folder):
                if combined_filename not in os.listdir(month_folder):
                    shutil.copy(combined_file_fullpath, month_folder)

        if len(xmls_list) > 0 and not any(combined_filename in item for item in files_list):
            logger.info("individual summaries are present but not combined")
            for file in xmls_list:
                self.append_columns(df_dict, file, title, namespace)
                tree = ET.parse(file)
                root = tree.getroot()
                summary = root.find('atom:entry/atom:summary', namespace).text
                df_dict["body"].append(summary)

    def preprocess_authors_name(self, author_tuple):
        author_tuple = tuple(s.replace('+', '').strip() for s in author_tuple)
        return author_tuple

    def add_utc_if_not_present(self, datetime_str):
        try:
            datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S%z")
            datetime_obj = datetime_obj.replace(tzinfo=pytz.UTC)
        except ValueError:
            datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
            timezone = pytz.UTC
            datetime_obj = datetime_obj.replace(tzinfo=timezone)
        return datetime_obj.isoformat(" ")

    def generate_new_emails_df(self, dict_data, dev_url):
        columns = ['_index', '_id', '_score']
        source_cols = ['body_type', 'created_at', 'id', 'title', 'body', 'type',
                       'url', 'authors']
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}

        current_directory = os.getcwd()

        if "lightning-dev" in dev_url:
            files_list = glob.glob(os.path.join(current_directory, "static", "lightning-dev", "**/*.xml"),
                                   recursive=True)
        else:
            files_list = glob.glob(os.path.join(current_directory, "static", "bitcoin-dev", "**/*.xml"), recursive=True)

        df_dict = {}
        for col in columns:
            df_dict[col] = []
        for col in source_cols:
            df_dict[col] = []

        for data in range(len(dict_data)):
            xmls_list = []
            number = get_id(dict_data[data]["_source"]["id"])
            title = dict_data[data]["_source"]["title"]
            xml_name = clean_title(title)
            file_name = f"{number}_{xml_name}.xml"
            combined_filename = f"combined_{xml_name}.xml"

            if not any(file_name in item for item in files_list):
                logger.info(f"{file_name} is not present")
                self.file_not_present_df(columns, source_cols, df_dict, files_list, dict_data, data,
                                         title, combined_filename, namespace)

            else:
                logger.info(f"{file_name} already exist")
                self.file_present_df(files_list, namespace, combined_filename, title, xmls_list, df_dict)

        emails_df = pd.DataFrame(df_dict)

        emails_df['authors'] = emails_df['authors'].apply(convert_to_tuple)
        emails_df = emails_df.drop_duplicates()
        emails_df['authors'] = emails_df['authors'].apply(self.preprocess_authors_name)
        emails_df['body'] = emails_df['body'].apply(preprocess_email)
        emails_df['title'] = emails_df['title'].apply(remove_multiple_whitespaces)
        logger.info(f"Shape of emails_df: {emails_df.shape}")
        return emails_df

    def start(self, dict_data, url):
        if len(dict_data) > 0:
            emails_df = self.generate_new_emails_df(dict_data, url)
            if len(emails_df) > 0:
                emails_df['created_at_org'] = emails_df['created_at'].astype(str)

                def generate_local_xml(cols, combine_flag, url):
                    month_name = month_dict[int(cols['created_at'].month)]
                    str_month_year = f"{month_name}_{int(cols['created_at'].year)}"

                    if "bitcoin-dev" in url:
                        if not os.path.exists(f"static/bitcoin-dev/{str_month_year}"):
                            create_folder(f"static/bitcoin-dev/{str_month_year}")
                        number = get_id(cols['id'])
                        xml_name = clean_title(cols['title'])
                        file_path = f"static/bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml"
                    else:
                        if not os.path.exists(f"static/lightning-dev/{str_month_year}"):
                            create_folder(f"static/lightning-dev/{str_month_year}")
                        number = get_id(cols['id'])
                        xml_name = clean_title(cols['title'])
                        file_path = f"static/lightning-dev/{str_month_year}/{number}_{xml_name}.xml"
                    if os.path.exists(file_path):
                        logger.info(f"{file_path} already exist")
                        if "bitcoin-dev" in url:
                            link = f'bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml'
                        else:
                            link = f'lightning-dev/{str_month_year}/{number}_{xml_name}.xml'
                        return link
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
                    if "bitcoin-dev" in url:
                        link = f'bitcoin-dev/{str_month_year}/{number}_{xml_name}.xml'
                    else:
                        link = f'lightning-dev/{str_month_year}/{number}_{xml_name}.xml'
                    return link

                # combine_summary_xml
                os_name = platform.system()
                logger.info(f"Operating System: {os_name}")
                titles = emails_df.sort_values('created_at')['title'].unique()
                logger.info(f"Total titles in data: {len(titles)}")
                for title_idx, title in tqdm(enumerate(titles)):
                    title_df = emails_df[emails_df['title'] == title]
                    title_df['authors'] = title_df['authors'].apply(convert_to_tuple)
                    title_df = title_df.drop_duplicates()
                    title_df['authors'] = title_df['authors'].apply(self.preprocess_authors_name)
                    title_df = title_df.sort_values(by='created_at', ascending=False)
                    logger.info(f"length of title_df: {len(title_df)}")
                    if len(title_df) < 1:
                        continue
                    if len(title_df) == 1:
                        generate_local_xml(title_df.iloc[0], "0", url)
                        continue
                    # body = title_df['body'].apply(str).tolist() + old_files_data_dict["summary_list"]
                    combined_body = '\n\n'.join(title_df['body'].apply(str))
                    # combined_body = '\n\n'.join(body)
                    xml_name = clean_title(title)
                    combined_links = list(title_df.apply(generate_local_xml, args=("1", url), axis=1))
                    combined_authors = list(
                        title_df.apply(lambda x: f"{x['authors'][0]} {x['created_at']}", axis=1))

                    month_year_group = \
                        title_df.groupby([title_df['created_at'].dt.month, title_df['created_at'].dt.year])

                    flag = False
                    std_file_path = ''
                    for idx, (month_year, _) in enumerate(month_year_group):
                        logger.info(f"Month and Year: {month_year}")
                        month_name = month_dict[int(month_year[0])]
                        str_month_year = f"{month_name}_{month_year[1]}"
                        if "bitcoin-dev" in url:
                            file_path = f"static/bitcoin-dev/{str_month_year}/combined_{xml_name}.xml"
                        else:
                            file_path = f"static/lightning-dev/{str_month_year}/combined_{xml_name}.xml"
                        combined_summary = create_summary(combined_body)
                        feed_data = {
                            'id': "2",
                            'title': 'Combined summary - ' + title,
                            'authors': combined_authors,
                            'url': title_df.iloc[0]['url'],
                            'links': combined_links,
                            'created_at': self.add_utc_if_not_present(title_df.iloc[0]['created_at_org']),
                            'summary': combined_summary
                        }
                        if not flag:
                            self.generate_xml(feed_data, file_path)
                            std_file_path = file_path
                            flag = True
                        else:
                            if os_name == "Windows":
                                shutil.copy(std_file_path, file_path)
                            elif os_name == "Linux":
                                os.system(f"cp {std_file_path} {file_path}")
            else:
                logger.info("No new files are found")
        else:
            logger.info("No input data found")
