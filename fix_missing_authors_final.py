#!/usr/bin/env python3
"""
Fix XMLs that have NO author tag at all by fetching from Elasticsearch
"""

import xml.etree.ElementTree as ET
import requests
from pathlib import Path

# Elasticsearch configuration
ES_INDEX = "bitcoin-search-august-23"
ES_URL = "https://my-test-es-deploy.es.us-central1.gcp.cloud.es.io"
ES_API_KEY = "MV9xanFvNEJ4Ti1oU21pWktWWkM6UDZGU2FwQ1NRNmFyMVVGNWJhVWliZw=="

ES_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"ApiKey {ES_API_KEY}"
}

ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}

# Files with NO author at all
FILES_TO_FIX = [
    "static/bitcoin-dev/April_2025/combined_Re-Against-Allowing-Quantum-Recovery-of-Bitcoin.xml",
    "static/bitcoin-dev/June_2025/combined_BIP39-Extension-for-Manual-Seed-Phrase-Creation.xml",
    "static/bitcoin-dev/Oct_2023/combined_Removing-channel-reserve-for-mobile-wallet-users.xml",
    "static/bitcoin-dev/Jan_2025/combined_UTXO-checkpoint-transactions.xml",
    "static/bitcoin-dev/May_2025/combined_BIP39-Extension-for-Manual-Seed-Phrase-Creation.xml",
    "static/bitcoin-dev/March_2025/combined_Re-Against-Allowing-Quantum-Recovery-of-Bitcoin.xml",
    "static/bitcoin-dev/March_2024/combined_Re-A-Free-Relay-Attack-Exploiting-RBF-Rule-6.xml"
]


def get_title_from_xml(xml_file):
    """Extract title from XML"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Look for title in entry
        title_elem = root.find('.//atom:entry/atom:title', ATOM_NS)
        if title_elem is not None and title_elem.text:
            return title_elem.text.strip().replace("Combined summary - ", "")
        
        # Look for title in root
        title_elem = root.find('.//atom:title', ATOM_NS)
        if title_elem is not None and title_elem.text:
            return title_elem.text.strip().replace("Combined summary - ", "")
        
        return None
    except Exception as e:
        print(f"❌ Error reading {xml_file}: {e}")
        return None


def get_authors_from_es(title):
    """Get authors from Elasticsearch based on title"""
    try:
        # Query ES for documents with this title
        query = {
            "query": {
                "match_phrase": {
                    "title": title
                }
            },
            "size": 10,
            "_source": ["authors", "title"]
        }
        
        url = f"{ES_URL}/{ES_INDEX}/_search"
        response = requests.post(url, json=query, headers=ES_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        
        # Collect all unique authors
        authors = set()
        for hit in hits:
            hit_authors = hit["_source"].get("authors", [])
            for author in hit_authors:
                if author and not ('UTC' in author or 'newest]' in author):
                    authors.add(author)
        
        return list(authors) if authors else None
        
    except Exception as e:
        print(f"❌ Error querying ES: {e}")
        return None


def add_authors_to_xml(xml_file, authors):
    """Add author tags to XML file"""
    try:
        # Parse XML
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Register namespace to avoid ns0 prefix
        ET.register_namespace('', 'http://www.w3.org/2005/Atom')
        
        # Find the entry element
        entry = root.find('.//atom:entry', ATOM_NS)
        if entry is None:
            print(f"⚠️  No entry element found in {xml_file}")
            return False
        
        # Find the published element (we'll insert authors after title, before published)
        title_elem = entry.find('.//atom:title', ATOM_NS)
        updated_elem = entry.find('.//atom:updated', ATOM_NS)
        
        if title_elem is None or updated_elem is None:
            print(f"⚠️  Missing required elements in {xml_file}")
            return False
        
        # Get the index where to insert
        title_index = list(entry).index(title_elem)
        updated_index = list(entry).index(updated_elem)
        
        # Insert authors after updated element
        insert_index = updated_index + 1
        
        # Add author elements
        for author_name in authors:
            author_elem = ET.Element('{http://www.w3.org/2005/Atom}author')
            name_elem = ET.SubElement(author_elem, '{http://www.w3.org/2005/Atom}name')
            name_elem.text = author_name
            entry.insert(insert_index, author_elem)
            insert_index += 1
        
        # Write back
        tree.write(xml_file, encoding='utf-8', xml_declaration=True)
        return True
        
    except Exception as e:
        print(f"❌ Error updating {xml_file}: {e}")
        return False


def main():
    print("="*80)
    print("🔧 FIXING XMLs WITH NO AUTHORS")
    print("="*80)
    
    fixed_count = 0
    failed_count = 0
    
    for xml_file_path in FILES_TO_FIX:
        xml_file = Path(xml_file_path)
        
        if not xml_file.exists():
            print(f"\n❌ File not found: {xml_file}")
            failed_count += 1
            continue
        
        print(f"\n[{FILES_TO_FIX.index(xml_file_path) + 1}/{len(FILES_TO_FIX)}] {xml_file.name}")
        
        # Get title
        title = get_title_from_xml(xml_file)
        if not title:
            print(f"   ❌ Could not extract title")
            failed_count += 1
            continue
        
        print(f"   Title: {title}")
        
        # Get authors from ES
        authors = get_authors_from_es(title)
        if not authors:
            print(f"   ⚠️  No authors found in Elasticsearch")
            failed_count += 1
            continue
        
        print(f"   ✓ Found {len(authors)} author(s): {', '.join(authors[:3])}")
        if len(authors) > 3:
            print(f"     ... and {len(authors) - 3} more")
        
        # Add authors to XML
        if add_authors_to_xml(xml_file, authors):
            print(f"   ✅ Fixed!")
            fixed_count += 1
        else:
            print(f"   ❌ Failed to update")
            failed_count += 1
    
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print(f"Total files: {len(FILES_TO_FIX)}")
    print(f"✅ Fixed: {fixed_count}")
    print(f"❌ Failed: {failed_count}")
    print("="*80)


if __name__ == "__main__":
    main()
