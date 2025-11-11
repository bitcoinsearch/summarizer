import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from loguru import logger
from src.config import ES_INDEX
from src.elasticsearch_utils import ElasticSearchClient


class AuthorRestorer:
    """Restore missing author tags in XML files that lost them during threading update"""
    
    def __init__(self):
        self.elastic_search = ElasticSearchClient()
    
    def has_authors(self, xml_file_path):
        """Check if XML file has author information (either old or new format)"""
        try:
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Check for old format authors
            authors = root.findall('.//atom:author/atom:name', namespaces)
            if authors:
                return True, 'old_format'
            
            # Check for new format threading (messages are in atom namespace)
            thread = root.find('.//atom:thread', namespaces)
            if thread is not None:
                messages = thread.findall('./atom:message', namespaces)
                if len(messages) > 0:
                    # Verify messages have authors
                    author_in_msg = thread.find('./atom:message/atom:author', namespaces)
                    if author_in_msg is not None:
                        return True, 'threaded'
            
            return False, None
        except Exception as e:
            logger.error(f"Error checking authors in {xml_file_path}: {e}")
            return False, None
    
    def extract_title_from_xml(self, xml_file_path):
        """Extract title from XML file"""
        try:
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            title_elem = root.find('.//atom:entry/atom:title', namespaces)
            if title_elem is not None:
                # Remove "Combined summary - " prefix
                title = title_elem.text.replace('Combined summary - ', '')
                return title
            return None
        except Exception as e:
            logger.error(f"Error extracting title from {xml_file_path}: {e}")
            return None
    
    def get_authors_from_es(self, title, dev_url):
        """Fetch author information from Elasticsearch"""
        try:
            title_dict_data = self.elastic_search.fetch_data_based_on_title(
                es_index=ES_INDEX, title=title, url=dev_url
            )
            
            if not title_dict_data:
                logger.warning(f"No data found in ES for title: {title}")
                return []
            
            # Sort by creation time
            title_dict_data.sort(key=lambda x: x['_source']['created_at'])
            
            authors = []
            for doc in title_dict_data:
                source = doc['_source']
                author_name = source.get('authors', ['Unknown'])[0] if source.get('authors') else 'Unknown'
                created_at = source.get('created_at', '')
                # Format: "AuthorName Timestamp" to match old format
                authors.append(f"{author_name} {created_at}")
            
            return authors
            
        except Exception as e:
            logger.error(f"Error fetching authors from ES for title '{title}': {e}")
            return []
    
    def restore_authors_in_xml(self, xml_file_path, authors):
        """Add missing authors back to XML file in old format"""
        try:
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Find the generator element (we'll insert authors after it)
            generator = root.find('.//atom:generator', namespaces)
            if generator is None:
                logger.error(f"Could not find generator element in {xml_file_path}")
                return False
            
            # Get the index of generator element
            generator_index = list(root).index(generator)
            
            # Insert author elements after generator
            for i, author in enumerate(authors):
                author_elem = ET.Element('{http://www.w3.org/2005/Atom}author')
                name_elem = ET.SubElement(author_elem, '{http://www.w3.org/2005/Atom}name')
                name_elem.text = author
                root.insert(generator_index + 1 + i, author_elem)
            
            # Pretty print and save
            rough_string = ET.tostring(root, 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            
            # Remove extra blank lines
            pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
            
            # Write back to file
            with open(xml_file_path, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            
            logger.success(f"✅ RESTORE: Added {len(authors)} authors to {xml_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ RESTORE: Error restoring authors in {xml_file_path}: {e}")
            return False
    
    def find_combined_xml_files(self, base_directory="static/bitcoin-dev"):
        """Find all combined XML files"""
        combined_files = []
        
        for root, _, files in os.walk(base_directory):
            for file in files:
                if file.startswith('combined_') and file.endswith('.xml'):
                    file_path = os.path.join(root, file)
                    combined_files.append(file_path)
        
        logger.info(f"📁 RESTORE: Found {len(combined_files)} combined XML files")
        return combined_files
    
    def restore_all_missing_authors(self):
        """Restore missing authors in all XML files that need it"""
        dev_url = "https://lists.linuxfoundation.org/pipermail/bitcoin-dev/"
        
        logger.info("🚀 RESTORE: Starting author restoration for bitcoin-dev")
        
        # Find all combined XML files
        combined_files = self.find_combined_xml_files()
        
        restored_count = 0
        skipped_count = 0
        error_count = 0
        
        for xml_file_path in combined_files:
            try:
                # Check if file has authors
                has_auth, format_type = self.has_authors(xml_file_path)
                
                if has_auth:
                    logger.info(f"✅ RESTORE: {xml_file_path} already has authors ({format_type})")
                    skipped_count += 1
                    continue
                
                logger.warning(f"⚠️ RESTORE: {xml_file_path} is missing authors!")
                
                # Extract title
                title = self.extract_title_from_xml(xml_file_path)
                if not title:
                    logger.error(f"❌ RESTORE: Could not extract title from {xml_file_path}")
                    error_count += 1
                    continue
                
                # Get authors from Elasticsearch
                authors = self.get_authors_from_es(title, dev_url)
                
                if not authors:
                    logger.error(f"❌ RESTORE: Could not get authors from ES for {xml_file_path}")
                    error_count += 1
                    continue
                
                # Restore authors in XML
                if self.restore_authors_in_xml(xml_file_path, authors):
                    restored_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"❌ RESTORE: Error processing {xml_file_path}: {e}")
                error_count += 1
        
        logger.success(f"🎉 RESTORE: Completed! Restored: {restored_count}, Skipped: {skipped_count}, Errors: {error_count}")


if __name__ == "__main__":
    restorer = AuthorRestorer()
    restorer.restore_all_missing_authors()

