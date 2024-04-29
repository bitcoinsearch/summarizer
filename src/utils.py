import datetime
import os
import re
from ast import literal_eval

import pandas as pd
import pytz
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from loguru import logger
from tqdm import tqdm

from src.config import TOKENIZER, CHATGPT
from src.gpt_utils import generate_chatgpt_summary, generate_summary, generate_title, generate_chatgpt_title, \
    consolidate_chatgpt_summary, consolidate_summary

CURRENT_TIME = datetime.datetime.now(datetime.timezone.utc)
CURRENT_TIMESTAMP = str(CURRENT_TIME.timestamp()).replace(".", "_")
logger.info(f"Current Time: {CURRENT_TIME}")

month_dict = {
    1: "Jan", 2: "Feb", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "Aug", 9: "Sept", 10: "Oct", 11: "Nov", 12: "Dec"
}


def add_utc_if_not_present(datetime_str, iso_format=True):
    """
    Parses the given datetime string and adds UTC timezone information if not already present.

    Args:
        datetime_str (str): The datetime string to parse.
        iso_format (bool, optional): Whether to return the result in ISO 8601 format. Default is True.

    Returns:
        datetime.datetime or str: If `iso_format` is True, returns the datetime string in ISO 8601 format with UTC timezone.
                                  Otherwise, returns a datetime object with UTC timezone.
    Raises:
        ValueError: If no valid date format is found for the given datetime string.
    """
    time_formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%fZ"
    ]
    for fmt in time_formats:
        try:
            datetime_obj = datetime.datetime.strptime(datetime_str, fmt)
            timezone = pytz.UTC
            datetime_obj = datetime_obj.replace(tzinfo=timezone)
            if iso_format:
                return datetime_obj.isoformat(" ")
            else:
                return datetime_obj
        except ValueError:
            pass
    raise ValueError("No valid date format found for string: " + datetime_str)


def remove_timestamps_from_author_names(author_list):
    """
    Removes timestamps from author names in the given list.

    Args:
        author_list (list of str): A list containing author names, possibly with timestamps.

    Returns:
        list of str: A list of unique author names with timestamps removed.
    """
    preprocessed_list = []
    for author in author_list:
        name = author.split(" ")[0:-2]
        preprocessed_list.append(' '.join(name))
    return list(set(preprocessed_list))


def convert_to_tuple(x):
    """
    Converts the input to a tuple.

    Args:
        x (str or any): The input to be converted. If a string, it's evaluated as a Python literal using `ast.literal_eval`.

    Returns:
        tuple: The input converted to a tuple.

    """
    try:
        if isinstance(x, str):
            x = literal_eval(x)
        return tuple(x)
    except ValueError:
        return (x,)


def clean_title(xml_name):
    """
    Cleans the title extracted from an XML file by replacing special characters with hyphens.

    Args:
        xml_name (str): The title extracted from an XML file.

    Returns:
        str: The cleaned title with special characters replaced by hyphens.

    """
    special_characters = ['/', ':', '@', '#', '$', '*', '&', '<', '>', '\\', '?']
    xml_name = re.sub(r'[^A-Za-z0-9]+', '-', xml_name)
    for sc in special_characters:
        xml_name = xml_name.replace(sc, "-")
    return xml_name


def get_id(id):
    """
    Extracts the last part of an ID string after splitting by hyphens.

    Args:
        id (str): The ID string.

    Returns:
        str: The last part of the ID string.

    """
    return str(id).split("-")[-1]


def create_folder(month_year):
    """
    Creates a folder with the given name if it doesn't exist.

    Args:
        month_year (str): The name of the folder to be created.

    """
    os.makedirs(month_year, exist_ok=True)


def remove_multiple_whitespaces(text):
    """
    Removes multiple whitespaces from the given text.

    Args:
        text (str): The input text.

    Returns:
        str: The text with multiple whitespaces replaced by a single whitespace.

    """
    return re.sub('\s+', ' ', text).strip()


def normalize_text(s, sep_token=" \n "):
    """
    Normalizes the given text by removing extra whitespaces, punctuation, and special characters.

    Args:
        s (str): The input text to be normalized.
        sep_token (str, optional): The separator token to be used. Default is ' \n '.

    Returns:
        str: The normalized text.

    """
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r". ,", "", s)
    s = s.replace("..", ".")
    s = s.replace(". .", ".")
    s = s.replace("\n", "")
    s = s.replace("#", "")
    s = s.strip()
    return s


def is_date(string, fuzzy=False):
    """
    Checks if the given string represents a date.

    Args:
        string (str): The input string to be checked.
        fuzzy (bool, optional): Whether to use fuzzy parsing. Default is False.

    Returns:
        bool: True if the string represents a date, False otherwise.

    """
    try:
        parse(string, fuzzy=fuzzy)
        return True
    except ValueError:
        return False


def preprocess_email(email_body):
    """
    Preprocesses the given email body by removing unnecessary parts and normalizing the text.

    Args:
        email_body (str): The email body to be preprocessed.

    Returns:
        str: The preprocessed and normalized email body.
    """
    email_body = email_body.split("-------------- next part --------------")[0]
    email_lines = email_body.split('\n')
    temp_ = []
    for line in email_lines:
        if line.startswith("On"):
            line = line.replace("-", " ")
            x = re.sub('\d', ' ', line)
            if is_date(x, fuzzy=True):
                continue
            if line.endswith("> wrote:"):
                continue
        if line.endswith("> wrote:"):
            continue
        if line.startswith("Le "):
            continue
        if line.endswith("?crit :"):
            continue
        if re.match(r'\d{4}-\d{2}-\d{2}', line):
            continue
        if line.startswith("From:") or line.strip().startswith("To") or line.strip().startswith("permalink"):
            continue
        if line.startswith("Sent with Proton Mail"):
            continue
        if line and not line.startswith('>'):
            if line.startswith('-- ') or line.startswith('[') or line.startswith('_____'):
                continue
            temp_.append(line)
    email_string = "\n".join(temp_)
    normalized_email_string = normalize_text(email_string)
    if len(normalized_email_string) == 0:
        return email_body
    else:
        return normalized_email_string


def scrape_email_data(url_):
    """
    Scrapes email data from the given URL and preprocesses it.

    Args:
        url_ (str): The URL of the email content.

    Returns:
        tuple: A tuple containing author name, timestamp, subject, and preprocessed email body.
    """
    r = requests.get(url_)
    body_soup = BeautifulSoup(r.content, 'html.parser').body
    subject = body_soup.find('h1').text
    author = body_soup.find('b').text
    timestamp = body_soup.find('i').text
    timestamp = parse(str(timestamp), fuzzy=True)
    timestamp = timestamp.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
    email_body = body_soup.find('pre').text
    normalized_email_body = preprocess_email(email_body)
    return author, timestamp, normalize_text(subject), normalized_email_body


def get_past_week_data(dataframe):
    """
    Retrieves data from the past week from the given DataFrame.

    Args:
        dataframe (pd.DataFrame): The DataFrame containing email data.

    Returns:
        pd.DataFrame: A DataFrame containing data from the past week.

    """
    dt_now = CURRENT_TIME
    dt_min = dt_now - datetime.timedelta(days=7)
    dataframe['timestamp'] = pd.to_datetime(dataframe['timestamp'], utc=True)
    sliced_df = dataframe[(dataframe['timestamp'] >= dt_min) & (dataframe['timestamp'] <= dt_now)]
    sliced_df.dropna(inplace=True)
    sliced_df.reset_index(drop=True, inplace=True)
    return sliced_df


def get_datetime_format(dataframe):
    """
    Converts the 'date' column in the DataFrame to a standard datetime format.

    Args:
        dataframe (pd.DataFrame): The DataFrame containing email data.

    Returns:
        pd.DataFrame: The DataFrame with the 'date' column converted to a standard datetime format.
    """
    date_list = []
    for i, r in dataframe.iterrows():
        date_string = str(r['date'])
        date_string = date_string.replace("?", " ").strip()
        date_list.append(date_string)
    dataframe['date'] = date_list
    dataframe['date'] = pd.to_datetime(dataframe['date'], utc=True)
    dataframe['date'] = pd.to_datetime(dataframe['date'], format='%Y-%m-%d %H:%M:%S', utc=True)
    dataframe['date'] = dataframe['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return dataframe


def collect_email_urls(base_url):
    urls_list = []
    # add current month
    month_route = f"{CURRENT_TIME.strftime('%Y-%B')}"
    email_thread_url = f"{base_url}/{month_route}/"
    urls_list.append(email_thread_url)

    # if current month is not past 7 days, add previous month as well
    if CURRENT_TIME.day < 7:
        prev_month = (CURRENT_TIME - relativedelta(months=1)).strftime('%Y-%B')
        email_thread_url = f"{base_url}/{prev_month}/"
        urls_list.append(email_thread_url)

    all_email_urls = []
    for base_url in urls_list:
        print(f"working on: {base_url}")
        scrape_url = "date.html"
        r = requests.get(base_url + scrape_url)
        soup = BeautifulSoup(r.content, 'html.parser')
        if soup.body:
            ul_soup = soup.body.findAll('ul')[1]
            li_rows = ul_soup.findAll('li')

            # get all emails urls
            email_urls = [base_url + str(i.a['href']).strip() for i in li_rows]
            all_email_urls.extend(email_urls)

    print(f"Fetched Urls: {len(all_email_urls)}")
    return all_email_urls


def scrape_email_urls(email_urls_list):
    df_list = []
    for i in tqdm(email_urls_list):
        auth_, timestamp_, sub_, email_ = scrape_email_data(i)
        df_dict = {
            "timestamp": timestamp_,
            "author": auth_,
            "subject": sub_,
            "email": email_,
            "email_url": i,
        }
        df_list.append(df_dict)
    # data frame of all emails
    emails_df = pd.DataFrame(df_list)

    # filter dataframe to get last week's data only
    df_week = get_past_week_data(emails_df)
    df_week['tokens'] = df_week['email'].apply(lambda x: len(TOKENIZER.encode(x)))

    os.makedirs("output", exist_ok=True)
    df_week.to_csv(f"output/df_week_{CURRENT_TIMESTAMP}.csv", index=False)
    return df_week


def get_email_thread_data(sub_df):
    sub_df.sort_values(by='timestamp', ascending=True, inplace=True)
    sub_df.dropna(inplace=True)
    sub_df.reset_index(drop=True, inplace=True)

    first_post_date = ""
    subject = ""
    num_of_replies = sub_df.shape[0]
    author = []
    urls = []
    generated_summary = []
    consolidated_summary = ""
    consolidated_title = ""

    for i, r in tqdm(sub_df.iterrows(), total=sub_df.shape[0]):
        if i == 0:
            first_post_date += r.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            subject += r.subject
        email_text = r.email
        auth = r.author
        url = r.email_url

        if CHATGPT:
            summary_ = generate_chatgpt_summary(email_text)
        else:
            summary_ = generate_summary(email_text)

        author.append(auth)
        urls.append(url)
        generated_summary.append(summary_)

    # consolidated summary
    summary_concat = "\n".join(generated_summary)

    if CHATGPT:
        consolidated_summary += consolidate_chatgpt_summary(summary_concat)
        consolidated_title += generate_chatgpt_title(summary_concat)
    else:
        consolidated_summary += consolidate_summary(summary_concat)
        consolidated_title += generate_title(summary_concat)

    data_dict = {
        "date": first_post_date,
        "subject": subject,
        "num_replies": num_of_replies,
        "authors": author,
        "urls": urls,
        "generated_summaries": generated_summary,
        "consolidated_title": consolidated_title,
        "consolidated_summary": consolidated_summary
    }
    return data_dict


def generate_newsletter_completion(df):
    grouped_df = df.groupby('subject')
    print(f"Number of threads found: {len(grouped_df)}")
    print("-----")

    data_records = []
    for index, sub_df in grouped_df:
        print(f"working on subject: {index}")
        data_dict = get_email_thread_data(sub_df)
        data_records.append(data_dict)
        print("-----")

    df_week_generated = pd.DataFrame(data_records)
    os.makedirs("output", exist_ok=True)
    df_week_generated.to_csv(f"output/df_week_generated_{CURRENT_TIMESTAMP}.csv", index=False)
    return df_week_generated


def save_html_file(df_week_generated, save_file_name):
    # open html
    file_handle = open(f"output/{save_file_name}", "w")

    html_title = "Sample Newsletter"
    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>{html_title}</title>
    <link rel="stylesheet" href="style.css">
    </head>
    <body>
    <h1 style="text-align:center; font-family:verdana" >Hello World!</h1>
    <br>
    '''
    file_handle.write(html)

    for idx, row in df_week_generated.iterrows():
        # get data
        subject = row.subject
        date = row.date
        num_replies = row.num_replies
        authors = row.authors
        urls = row.urls
        title = row.consolidated_title
        summary = row.consolidated_summary

        # write subjects and all
        html = f"<hr style='border-top: dotted 2px; '><h2 style='text-align:center; font-family:verdana;'>{subject}</h2><b>Date: </b><i>{date}</i><p>Number of replies: {num_replies}</p>"
        file_handle.write(html)

        # write title and summary
        html = f"<h3 style='text-align:center; font-family:verdana; color:#282828;'>{title}</h3><p>{summary}</p><br><b>References:</b>"
        file_handle.write(html)

        for i in range(len(urls)):
            author = authors[i]
            url = urls[i]
            html = f"<ul><li>{author}: <a href='{url}'>{subject}</a></li></ul>"
            file_handle.write(html)

        html = f"<br>"
        file_handle.write(html)

    html = "</body></html>"
    file_handle.write(html)
    file_handle.close()

    return f"output/{save_file_name}.html"
