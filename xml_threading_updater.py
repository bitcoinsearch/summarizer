import os
import time
from datetime import datetime
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from loguru import logger
import warnings

from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient
from src.xml_utils import GenerateXML

warnings.filterwarnings("ignore")


class XMLThreadingUpdater:
    def __init__(self):
        self.elastic_search = ElasticSearchClient()
        self.gen = GenerateXML()

    def has_threading_structure(self, xml_file_path):
        """Check if XML file already has threading structure"""
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            return root.find('.//{http://www.w3.org/2005/Atom}thread') is not None
        except Exception as e:
            logger.error(f"Error checking threading structure in {xml_file_path}: {e}")
            return False

    def extract_existing_summary_and_metadata(self, xml_file_path):
        """Extract existing summary and metadata from XML file"""
        try:
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Extract existing data
            title_elem = root.find('.//atom:entry/atom:title', namespaces)
            title = title_elem.text if title_elem is not None else None
            
            summary_elem = root.find('.//atom:entry/atom:summary', namespaces)
            summary = summary_elem.text if summary_elem is not None else None
            
            url_elem = root.find('.//atom:entry/atom:link', namespaces)
            url = url_elem.get('href') if url_elem is not None else None
            
            published_elem = root.find('.//atom:entry/atom:published', namespaces)
            published = published_elem.text if published_elem is not None else None
            
            # Extract links to individual XML files
            links = []
            link_elements = root.findall('.//atom:link[@rel="alternate"]', namespaces)
            for link_elem in link_elements:
                href = link_elem.get('href')
                if href:
                    links.append(href)
            
            return {
                'title': title,
                'summary': summary,
                'url': url,
                'published': published,
                'links': links
            }
        except Exception as e:
            logger.error(f"Error extracting data from {xml_file_path}: {e}")
            return None

    def get_threading_data_for_title(self, title, dev_url):
        """Fetch threading data from Elasticsearch for a specific title"""
        try:
            title_dict_data = self.elastic_search.fetch_data_based_on_title(
                es_index=ES_INDEX, title=title, url=dev_url
            )
            
            if not title_dict_data:
                logger.warning(f"No data found in ES for title: {title}")
                return []
            
            thread_data = []
            logger.info(f"🔍 THREADING UPDATER: Found {len(title_dict_data)} documents for title: {title}")
            
            # Sort by creation time to get proper chronological order
            title_dict_data.sort(key=lambda x: x['_source']['created_at'])
            
            for display_position, doc in enumerate(title_dict_data):
                source = doc['_source']
                
                # Extract anchor ID from document ID
                anchor_id = ''
                if source.get('id'):
                    doc_id = str(source['id'])
                    if 'm' in doc_id and len(doc_id) > 20:
                        parts = doc_id.split('-m')
                        if len(parts) > 1:
                            anchor_id = 'm' + parts[-1]
                
                thread_item = {
                    'author': source.get('authors', ['Unknown'])[0] if source.get('authors') else 'Unknown',
                    'created_at': source.get('created_at', ''),
                    'thread_depth': source.get('thread_depth', 0),
                    'thread_position': display_position,
                    'reply_to_author': source.get('reply_to_author', ''),
                    'parent_id': source.get('parent_id', ''),
                    'anchor_id': anchor_id
                }
                thread_data.append(thread_item)
                
                logger.info(f"    📧 THREADING UPDATER: #{display_position}: '{thread_item['author']}' depth={thread_item['thread_depth']} -> '{thread_item['reply_to_author']}' anchor='{anchor_id}'")
            
            return thread_data
            
        except Exception as e:
            logger.error(f"Error fetching threading data for title '{title}': {e}")
            return []

    def update_xml_with_threading(self, xml_file_path, thread_data, existing_data):
        """Update XML file with threading structure while preserving existing summary"""
        try:
            logger.info(f"🔄 THREADING UPDATER: Updating {xml_file_path} with threading structure")
            
            # Create new XML structure with threading
            feed = ET.Element('feed', xmlns='http://www.w3.org/2005/Atom')
            
            # Add basic feed metadata
            ET.SubElement(feed, 'id').text = "2"
            ET.SubElement(feed, 'title').text = existing_data['title']
            ET.SubElement(feed, 'updated').text = datetime.now().isoformat() + '+00:00'
            
            # Add generator info
            generator = ET.SubElement(feed, 'generator', uri='https://lkiesow.github.io/python-feedgen', version='0.9.0')
            generator.text = 'python-feedgen'
            
            # Add threading structure if we have thread data
            if thread_data:
                logger.info(f"📋 THREADING UPDATER: Adding threading structure with {len(thread_data)} messages")
                thread_element = ET.SubElement(feed, 'thread')
                self.gen._build_threaded_structure(thread_element, thread_data)
            else:
                logger.warning("⚠️ THREADING UPDATER: No thread data available, keeping flat structure")
            
            # Add links to individual XML files
            for link in existing_data['links']:
                ET.SubElement(feed, 'link', href=link, rel='alternate')
            
            # Add main entry with existing summary (PRESERVE EXISTING SUMMARY)
            entry = ET.SubElement(feed, 'entry')
            ET.SubElement(entry, 'id').text = "2"
            ET.SubElement(entry, 'title').text = existing_data['title']
            ET.SubElement(entry, 'updated').text = datetime.now().isoformat() + '+00:00'
            ET.SubElement(entry, 'link', href=existing_data['url'], rel='alternate')
            ET.SubElement(entry, 'published').text = existing_data['published']
            ET.SubElement(entry, 'summary').text = existing_data['summary']  # KEEP EXISTING SUMMARY
            
            # Pretty print and save XML
            rough_string = ET.tostring(feed, 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            
            # Remove extra blank lines
            pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
            
            # Write updated XML file
            with open(xml_file_path, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            
            logger.success(f"✅ THREADING UPDATER: Successfully updated {xml_file_path} with threading structure")
            return True
            
        except Exception as e:
            logger.error(f"❌ THREADING UPDATER: Error updating {xml_file_path}: {e}")
            return False

    def find_combined_xml_files(self, base_directory="static/bitcoin-dev"):
        """Find all combined XML files that need threading updates"""
        combined_files = []
        
        for root, _, files in os.walk(base_directory):
            for file in files:
                if file.startswith('combined_') and file.endswith('.xml'):
                    file_path = os.path.join(root, file)
                    combined_files.append(file_path)
        
        logger.info(f"📁 THREADING UPDATER: Found {len(combined_files)} combined XML files")
        return combined_files

    def extract_title_from_filename(self, xml_file_path):
        """Extract the original title from combined XML filename"""
        try:
            # Get filename without path and extension
            filename = os.path.basename(xml_file_path)
            
            # Try to extract title from existing XML first
            existing_data = self.extract_existing_summary_and_metadata(xml_file_path)
            if existing_data and existing_data['title']:
                # Remove "Combined summary - " prefix to get original title
                original_title = existing_data['title'].replace('Combined summary - ', '')
                return original_title
            
            logger.warning(f"Could not extract title from {xml_file_path}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting title from {xml_file_path}: {e}")
            return None

    def update_all_threading(self, start_year=None):
        """Update all combined XML files with threading structure"""
        dev_url = "https://gnusha.org/pi/bitcoindev/"  # Only bitcoin-dev
        
        logger.info("🚀 THREADING UPDATER: Starting threading update for bitcoin-dev")
        if start_year:
            logger.info(f"📅 THREADING UPDATER: Processing from year {start_year}")
        
        # Find all combined XML files
        combined_files = self.find_combined_xml_files()
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for xml_file_path in combined_files:
            try:
                # Skip if filtering by year
                if start_year:
                    # Extract year from path (e.g., "March_2022")
                    path_parts = xml_file_path.split('/')
                    for part in path_parts:
                        if '_' in part and part.split('_')[-1].isdigit():
                            file_year = int(part.split('_')[-1])
                            if file_year < int(start_year):
                                logger.info(f"⏭️ THREADING UPDATER: Skipping {xml_file_path} (year {file_year} < {start_year})")
                                skipped_count += 1
                                continue
                            break
                
                # Check if already has threading
                if self.has_threading_structure(xml_file_path):
                    logger.info(f"✅ THREADING UPDATER: {xml_file_path} already has threading structure")
                    skipped_count += 1
                    continue
                
                logger.info(f"🔄 THREADING UPDATER: Processing {xml_file_path}")
                
                # Extract existing data
                existing_data = self.extract_existing_summary_and_metadata(xml_file_path)
                if not existing_data:
                    logger.error(f"❌ THREADING UPDATER: Could not extract data from {xml_file_path}")
                    error_count += 1
                    continue
                
                # Extract title
                title = self.extract_title_from_filename(xml_file_path)
                if not title:
                    logger.error(f"❌ THREADING UPDATER: Could not extract title from {xml_file_path}")
                    error_count += 1
                    continue
                
                # Get threading data from Elasticsearch
                thread_data = self.get_threading_data_for_title(title, dev_url)
                
                # Update XML with threading
                if self.update_xml_with_threading(xml_file_path, thread_data, existing_data):
                    updated_count += 1
                else:
                    error_count += 1
                
                # Small delay to avoid overwhelming the system
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"❌ THREADING UPDATER: Error processing {xml_file_path}: {e}")
                error_count += 1
        
        logger.success(f"🎉 THREADING UPDATER: Completed! Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}")


if __name__ == "__main__":
    # Get parameters from environment or command line
    start_year = os.environ.get('START_YEAR')
    update_threading_only = os.environ.get('UPDATE_THREADING_ONLY', 'false').lower() == 'true'
    
    if len(sys.argv) > 1:
        start_year = sys.argv[1] if sys.argv[1] else None
    
    updater = XMLThreadingUpdater()
    
    if update_threading_only or start_year:
        logger.info("🧵 THREADING UPDATER: Running in threading update mode")
        updater.update_all_threading(start_year=start_year)
    else:
        logger.info("ℹ️ THREADING UPDATER: No threading update requested")
