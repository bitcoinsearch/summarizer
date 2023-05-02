import schedule
import time
from generate_xmls import GenerateXML


def generate_xml():
    gen = GenerateXML()
    # scrap data and save json and then pass it to xml
    json_path = "./data/bitcoin-search-index-revamped.json"
    gen.start(json_path)


schedule.every().day.at("23:00").do(generate_xml)

while True:
    schedule.run_pending()
    time.sleep(1)
