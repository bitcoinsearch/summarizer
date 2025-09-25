#!/usr/bin/env python3
"""
Script to update existing XML files with new threading structure
without regenerating AI content.

This script:
1. Goes through XML files year by year
2. Fetches threading data from Elasticsearch
3. Updates XML files with threading structure while preserving AI content
4. Does NOT regenerate AI summaries
"""

import os
import sys
import glob
import xml.etree.ElementTree as ET
from datetime import datetime
import argparse
from loguru import logger
import traceback

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import GenerateXML, XMLReader, get_base_directory
from src.config import ES_INDEX
# from src.utils import clean_title  # Not needed for this script

class ThreadingUpdater:
    def __init__(self):
        self.es_client = ElasticSearchClient()
        self.xml_generator = GenerateXML()
        self.xml_reader = XMLReader()
        
        # Available dev URLs
        self.dev_urls = [
            "https://delvingbitcoin.org/",
            "https://gnusha.org/pi/bitcoindev/",
            "https://mailing-list.bitcoindevs.xyz/bitcoindev/"
        ]
    
    def get_xml_files_by_year(self, year):
        """Get all XML files for a specific year"""
        xml_files = []
        
        for dev_url in self.dev_urls:
            directory = get_base_directory(dev_url)
            pattern = f"static/{directory}/*_{year}/*.xml"
            files = glob.glob(pattern)
            xml_files.extend(files)
        
        logger.info(f"Found {len(xml_files)} XML files for year {year}")
        return xml_files
    
    def get_combined_xml_files_by_year(self, year):
        """Get only combined XML files for a specific year"""
        xml_files = self.get_xml_files_by_year(year)
        combined_files = [f for f in xml_files if 'combined_' in os.path.basename(f)]
        logger.info(f"Found {len(combined_files)} combined XML files for year {year}")
        return combined_files
    
    def extract_thread_info_from_xml(self, xml_file):
        """Extract thread information from existing XML file"""
        try:
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Get title and URL to identify the thread
            title_elem = root.find('.//atom:entry/atom:title', namespaces)
            url_elem = root.find('.//atom:entry/atom:link', namespaces)
            
            if title_elem is None or url_elem is None:
                logger.warning(f"Could not extract thread info from {xml_file}")
                return None
            
            title = title_elem.text
            url = url_elem.get('href')
            
            # Remove "Combined summary - " prefix if present
            if title.startswith("Combined summary - "):
                title = title[19:]
            
            # Determine the dev URL from the XML link
            dev_url = None
            if "delvingbitcoin" in url:
                dev_url = "https://delvingbitcoin.org/"
            elif "bitcoindev" in url:
                dev_url = "https://mailing-list.bitcoindevs.xyz/bitcoindev/"
            elif "gnusha.org" in url:
                dev_url = "https://gnusha.org/pi/bitcoindev/"
            
            return {
                'title': title,
                'url': url,
                'dev_url': dev_url,
                'xml_file': xml_file
            }
            
        except (ET.ParseError, AttributeError, KeyError) as e:
            logger.error(f"Error extracting thread info from {xml_file}: {e}")
            return None
    
    def fetch_threading_data_for_thread(self, title, dev_url):
        """Fetch threading data from Elasticsearch for a specific thread"""
        try:
            logger.info(f"Fetching threading data for: '{title}' from {dev_url}")
            
            # Use the existing method to fetch data based on title
            thread_data = self.es_client.fetch_data_based_on_title(
                es_index=ES_INDEX, 
                title=title, 
                url=dev_url
            )
            
            if not thread_data:
                logger.warning(f"No threading data found for thread: {title}")
                return []
            
            logger.info(f"Found {len(thread_data)} documents for thread: {title}")
            
            # Extract threading information from each document
            threading_info = []
            for i, doc in enumerate(thread_data):
                source = doc.get('_source', {})
                
                # Extract anchor ID from document ID
                anchor_id = ''
                doc_id = source.get('id', '')
                if 'm' in doc_id and len(doc_id) > 20:
                    parts = doc_id.split('-m')
                    if len(parts) > 1:
                        anchor_id = 'm' + parts[-1]
                
                thread_item = {
                    'author': source.get('authors', ['Unknown'])[0] if source.get('authors') else 'Unknown',
                    'created_at': source.get('created_at', ''),
                    'thread_depth': source.get('thread_depth', 0),
                    'thread_position': source.get('thread_position', i),
                    'reply_to_author': source.get('reply_to_author', ''),
                    'parent_id': source.get('parent_id', ''),
                    'anchor_id': anchor_id
                }
                threading_info.append(thread_item)
            
            # Sort by thread_position to maintain proper order
            threading_info.sort(key=lambda x: x.get('thread_position', 0))
            
            logger.success(f"Extracted threading data for {len(threading_info)} messages")
            return threading_info
            
        except (ConnectionError, TimeoutError, KeyError) as e:
            logger.error(f"Error fetching threading data for {title}: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def update_xml_with_threading(self, xml_file, threading_data):
        """Update XML file with threading structure while preserving content"""
        try:
            logger.info(f"Updating XML file: {xml_file}")
            
            # Read existing XML to preserve the summary content
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Extract existing content we want to preserve
            id_elem = root.find('.//atom:entry/atom:id', namespaces)
            title_elem = root.find('.//atom:entry/atom:title', namespaces)
            summary_elem = root.find('.//atom:entry/atom:summary', namespaces)
            published_elem = root.find('.//atom:entry/atom:published', namespaces)
            url_elem = root.find('.//atom:entry/atom:link', namespaces)
            links = root.findall('.//atom:link[@rel="alternate"]', namespaces)
            
            if not all([id_elem, title_elem, summary_elem, published_elem, url_elem]):
                logger.error(f"Missing required elements in {xml_file}")
                return False
            
            # Prepare feed data with preserved content
            feed_data = {
                'id': id_elem.text,
                'title': title_elem.text,
                'authors': [],  # Will be filled from threading data
                'url': url_elem.get('href'),
                'links': [link.get('href') for link in links],
                'created_at': published_elem.text,
                'summary': summary_elem.text
            }
            
            # Generate new XML with threading structure
            if threading_data and len(threading_data) > 0:
                logger.info(f"Generating threaded XML with {len(threading_data)} threading items")
                self.xml_generator.generate_threaded_xml(feed_data, xml_file, threading_data)
                logger.success(f"✅ Updated {xml_file} with threading structure")
                return True
            else:
                logger.warning(f"No threading data available for {xml_file}, skipping")
                return False
                
        except (ET.ParseError, IOError, AttributeError) as e:
            logger.error(f"Error updating XML file {xml_file}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def process_year(self, year, dry_run=False):
        """Process all combined XML files for a specific year"""
        logger.info(f"🗓️ Processing year: {year}")
        
        # Get all combined XML files for the year
        combined_files = self.get_combined_xml_files_by_year(year)
        
        if not combined_files:
            if year < 2025:
                logger.info(f"No combined XML files found for year {year} - skipping (only updating existing files for years before 2025)")
            else:
                logger.info(f"No combined XML files found for year {year}")
            return
        
        # For years before 2025, we only update existing XMLs, don't create new ones
        if year < 2025:
            logger.info(f"⚠️ Year {year} < 2025: Will ONLY update existing XML files, no new files will be created")
        
        success_count = 0
        error_count = 0
        
        for xml_file in combined_files:
            try:
                logger.info(f"\n📄 Processing: {xml_file}")
                
                # Extract thread information from XML
                thread_info = self.extract_thread_info_from_xml(xml_file)
                if not thread_info:
                    logger.error(f"Could not extract thread info from {xml_file}")
                    error_count += 1
                    continue
                
                # Check if threading structure already exists
                with open(xml_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if '<thread>' in content or '<message' in content:
                        logger.info(f"⏭️ XML file already has threading structure, skipping: {xml_file}")
                        continue
                
                # Fetch threading data from Elasticsearch
                threading_data = self.fetch_threading_data_for_thread(
                    thread_info['title'], 
                    thread_info['dev_url']
                )
                
                if not threading_data:
                    logger.warning(f"No threading data found for {xml_file}")
                    error_count += 1
                    continue
                
                if dry_run:
                    logger.info(f"🔍 DRY RUN: Would update {xml_file} with {len(threading_data)} threading items")
                    success_count += 1
                else:
                    # Update XML with threading structure
                    if self.update_xml_with_threading(xml_file, threading_data):
                        success_count += 1
                    else:
                        error_count += 1
                        
            except (IOError, ET.ParseError, ConnectionError) as e:
                logger.error(f"Error processing {xml_file}: {e}")
                error_count += 1
        
        logger.info(f"\n📊 Year {year} Summary:")
        logger.info(f"   ✅ Successfully processed: {success_count}")
        logger.info(f"   ❌ Errors: {error_count}")
        logger.info(f"   📁 Total files: {len(combined_files)}")
    
    def run(self, years=None, dry_run=False):
        """Run the threading update process"""
        if years is None:
            # Default to last few years if no specific years provided
            current_year = datetime.now().year
            years = list(range(2022, current_year + 1))
        
        logger.info("🚀 Starting threading structure update")
        logger.info(f"📅 Years to process: {years}")
        logger.info(f"🔍 Dry run mode: {dry_run}")
        
        total_errors = 0
        
        for year in years:
            try:
                self.process_year(year, dry_run)
            except (IOError, ConnectionError) as e:
                logger.error(f"Failed to process year {year}: {e}")
                total_errors += 1
        
        logger.info("\n🎯 Overall Summary:")
        logger.info(f"   📅 Years processed: {len(years)}")
        logger.info("   🔍 DRY RUN COMPLETED" if dry_run else "   ✅ UPDATE COMPLETED")


def main():
    parser = argparse.ArgumentParser(description='Update XML files with threading structure')
    parser.add_argument('--years', nargs='+', type=int, 
                        help='Years to process (e.g., --years 2024 2025)')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be updated without making changes')
    parser.add_argument('--single-year', type=int,
                        help='Process only a single year')
    
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    updater = ThreadingUpdater()
    
    if args.single_year:
        years = [args.single_year]
    elif args.years:
        years = args.years
    else:
        # Default: process recent years
        current_year = datetime.now().year
        years = list(range(2023, current_year + 1))
    
    try:
        updater.run(years=years, dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("❌ Process interrupted by user")
        sys.exit(1)
    except OSError as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
