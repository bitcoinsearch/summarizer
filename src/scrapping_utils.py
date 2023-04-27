import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from tqdm import tqdm
import re
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
import pytz
import datetime

from src.utils import is_date, normalize_text, CURRENT_TIME, CURRENT_TIMESTAMP, get_past_week_data
from src import config


def preprocess_email(email_body):
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
        if line and not line.startswith('>'):
            if line.startswith('-- ') or line.startswith('[') or line.startswith('_____'):
                continue
            temp_.append(line)
    email_string = "\n".join(temp_)
    normalized_email_string = normalize_text(email_string)
    return normalized_email_string


def scrape_email_data(url_):
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
    df_week['tokens'] = df_week['email'].apply(lambda x: len(config.TOKENIZER.encode(x)))

    os.makedirs("output", exist_ok=True)
    df_week.to_csv(f"output/df_week_{CURRENT_TIMESTAMP}.csv", index=False)
    return df_week
